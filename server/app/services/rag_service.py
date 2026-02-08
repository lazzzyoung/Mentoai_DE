import logging
from typing import Any, TypedDict

from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    HarmBlockThreshold,
    HarmCategory,
)
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.core.config import Settings
from server.app.repositories.user_repository import UserRepository
from server.app.schemas.v1 import RoadmapResponseV1
from server.app.schemas.v2 import AnalysisResultV2, JobRecommendation, RoadmapResponseV2
from server.app.schemas.v3 import (
    ActionItem,
    DetailedAnalysisResponse,
    JobSummaryList,
    RecommendationListResponse,
)

logger = logging.getLogger(__name__)


ROADMAP_V1_PROMPT = """
[사용자] {user_specs}
[채용공고] {context}
합격을 위한 전략적 로드맵을 Markdown으로 작성해주세요.
"""

ROADMAP_V2_PROMPT = """
사용자 스펙과 공고를 비교하여 JSON으로 응답하세요. 마크다운 사용 금지.
[프로필] {user_specs}
[공고] {context}
{format_instructions}
"""

RECOMMENDATION_PROMPT = """
당신은 아주 깐깐하고 엄격한 IT 면접관입니다.
[사용자 프로필]과 [공고 목록]을 비교하여 냉정하게 적합도 점수를 매기세요.

[사용자 프로필] {user_specs}
[공고 목록] {jobs_context}

**채점 기준 (Strict Scoring):**
1. **기본 점수는 50점**에서 시작하세요.
2. **감점 요인**:
   - 공고가 '시니어(4년 이상)'를 요구하는데 사용자가 '신입/주니어'라면 **무조건 70점 미만**으로 채점하세요.
   - 클라우드(AWS/GCP), Kubernetes, 운영 경험 등 핵심 역량이 부족하면 가차 없이 감점하세요.
3. **가산 요인**: 기술 스택(Spark, Kafka 등)이 정확히 일치할 때만 점수를 올리세요.
4. **최종 점수**: 보통 60~85점 사이가 나와야 정상입니다. 90점 이상은 완벽하게 일치할 때만 주세요.
5. match_score, reason, job_id, company, title 필드를 포함하여 JSON으로 응답하세요.

**출력 포맷 (JSON):**
{format_instructions}
"""

DETAIL_ANALYSIS_PROMPT = """
당신은 IT 대기업 및 유니콘 스타트업의 **시니어 테크 리드(Tech Lead)**이자 채용 최종 결정권자입니다.
지원자의 이력서와 공고를 비교 분석하여, 당장 실천 가능한 **'합격 치트키'** 수준의 전략을 수립하세요.

[지원자 프로필] {user_specs}
[목표 공고] {company} / {title} / {content}

**작성 지침 (Deep Dive):**

1. **current_score (냉철한 평가)**:
   - 50~85점 사이로 책정하되, '왜 감점되었는지'를 분석하여 아래 액션 플랜에 녹여내세요.

2. **required_tech_stack (핵심 파악)**:
   - 공고에 나열된 기술 중, 지원자가 없으면 서류 광탈할 만한 **Critical Stack** 3~5가지만 엄선하세요.

3. **action_plan (초구체적 실행 가이드)**:
   - 추상적인 조언(예: "Kubernetes 공부하기")은 **절대 금지**입니다.
   - **How-to를 포함한 시나리오**를 제시하세요.
   - **예시**:
     - (Bad) "클라우드 공부하세요."
     - (Good) "현재 보유한 FastAPI 프로젝트를 Docker 이미지로 빌드하고, **AWS EKS(Free Tier)**에 배포하는 실습을 하세요. 이때 **Terraform**으로 인프라를 프로비저닝하여 'IaC 경험'을 포트폴리오에 한 줄 추가해야 합니다."
     - (Good) "지원자는 Spark 경험이 있으니, **Airflow**와 연동하여 '매일 09시에 S3 데이터를 긁어와 마트를 생성하는 DAG'를 구현하고 깃허브에 올리세요."

4. **interview_tip (면접관의 시선)**:
   - 해당 회사의 도메인(핀테크, 커머스, AI 등)과 기술 스택을 결합한 **예상 질문**을 던지고, **모범 답안의 키워드**를 알려주세요.

**출력 포맷 (JSON):**
{format_instructions}
"""


class UserInfo(TypedDict):
    username: str
    desired_job: str
    career_years: int
    skills: list[str]


class JobContext(TypedDict):
    job_id: int
    company: str
    title: str
    content: str


class DetailedAnalysisPayload(BaseModel):
    current_score: int
    max_score: int = 100
    analysis_summary: str
    required_tech_stack: list[str]
    action_plan: list[ActionItem]
    interview_tip: str


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        logger.info("Loading Embedding Model...")
        embeddings = HuggingFaceEmbeddings(
            model_name="BM-K/KoSimCSE-roberta-multitask",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

        logger.info("Connecting to Qdrant at %s", self.settings.qdrant_url)
        self.client = QdrantClient(url=self.settings.qdrant_url)
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.settings.collection_name,
            embedding=embeddings,
            content_payload_key="full_text",
            metadata_payload_key="metadata",
        )

        logger.info("Initializing Google Gemini model...")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            google_api_key=self.settings.google_api_key,
            temperature=0.3,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
        )

    async def _fetch_user_info(self, user_id: int, session: AsyncSession) -> UserInfo:
        user_repository = UserRepository(session)
        user_info = await user_repository.fetch_user_profile(user_id)
        if not user_info:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "username": user_info.get("username") or "",
            "desired_job": user_info.get("desired_job") or "",
            "career_years": int(user_info.get("career_years") or 0),
            "skills": list(user_info.get("skills") or []),
        }

    def _build_user_query_text(
        self, user_info: UserInfo, include_career: bool = False
    ) -> str:
        base_query = (
            f"희망직무: {user_info['desired_job']}, "
            f"보유기술: {', '.join(user_info['skills'])}"
        )

        if include_career:
            return f"{base_query}, 경력: {user_info['career_years']}년"
        return base_query

    def _similarity_search(self, query_text: str, limit: int) -> list[Document]:
        return self.vector_store.similarity_search(query_text, k=limit)

    @staticmethod
    def _format_docs(docs: list[Document], content_limit: int) -> str:
        return "\n".join(
            [
                f"기업: {doc.metadata.get('company')}\n"
                f"제목: {doc.metadata.get('position')}\n"
                f"내용: {doc.page_content[:content_limit]}"
                for doc in docs
            ]
        )

    def _fetch_job_payload(self, doc_id: int) -> dict[str, Any] | None:
        try:
            points = self.client.retrieve(
                collection_name=self.settings.collection_name,
                ids=[doc_id],
                with_payload=True,
            )
            if not points:
                return None

            payload = points[0].payload
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning("Metadata fetch failed for ID %s: %s", doc_id, exc)
            return None

    @staticmethod
    def _normalize_doc_id(doc: Document) -> int | None:
        raw_id = doc.metadata.get("id") or doc.metadata.get("_id")
        if raw_id is None:
            return None

        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None

    def _build_jobs_context(self, docs: list[Document]) -> list[JobContext]:
        context: list[JobContext] = []
        for doc in docs:
            doc_id = self._normalize_doc_id(doc)
            company = str(doc.metadata.get("company") or "미상")
            title = str(doc.metadata.get("position") or "미상")
            content = doc.page_content

            if doc_id is not None:
                payload = self._fetch_job_payload(doc_id)
                if payload:
                    company = str(payload.get("company") or company)
                    title = str(payload.get("position") or title)
                    content = str(payload.get("full_text") or content)

            context.append(
                {
                    "job_id": doc_id or 0,
                    "company": company,
                    "title": title,
                    "content": content[:300],
                }
            )
        return context

    async def get_user_specs(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> dict[str, Any]:
        user_repository = UserRepository(session)
        user_specs = await user_repository.fetch_user_specs(user_id)
        if not user_specs:
            raise HTTPException(status_code=404, detail="User not found")
        return user_specs

    def test_gemini_connection(self, prompt: str = "안녕") -> dict[str, str]:
        try:
            response = self.llm.invoke(prompt)
            return {"gemini_response": str(response.content)}
        except Exception as exc:
            logger.error("Gemini 연결 테스트 실패: %s", exc)
            raise HTTPException(
                status_code=500, detail="Gemini connection failed"
            ) from exc

    async def generate_career_roadmap_v1(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> RoadmapResponseV1:
        try:
            user_info = await self._fetch_user_info(user_id, session)
            user_query_text = self._build_user_query_text(user_info)

            retrieved_docs = self._similarity_search(user_query_text, limit=3)
            if not retrieved_docs:
                return RoadmapResponseV1(
                    user_name=user_info["username"],
                    recommended_jobs=[],
                    analysis_result="공고 없음",
                )

            prompt = ChatPromptTemplate.from_template(ROADMAP_V1_PROMPT)
            chain = prompt | self.llm | StrOutputParser()
            analysis_result = chain.invoke(
                {
                    "user_specs": user_query_text,
                    "context": self._format_docs(retrieved_docs, content_limit=300),
                }
            )

            recommended_jobs = [
                str(doc.metadata.get("position") or "미상") for doc in retrieved_docs
            ]

            return RoadmapResponseV1(
                user_name=user_info["username"],
                recommended_jobs=recommended_jobs,
                analysis_result=analysis_result,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("V1 roadmap 생성 실패: %s", exc)
            raise HTTPException(
                status_code=500, detail="V1 roadmap generation failed"
            ) from exc

    async def generate_career_roadmap_v2(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> RoadmapResponseV2:
        try:
            user_info = await self._fetch_user_info(user_id, session)
            user_query_text = self._build_user_query_text(user_info)

            retrieved_docs = self._similarity_search(user_query_text, limit=3)
            if not retrieved_docs:
                return RoadmapResponseV2(
                    user_name=user_info["username"],
                    recommended_jobs=[],
                    analysis_result=AnalysisResultV2(
                        current_score=0,
                        summary="공고 없음",
                        gap_analysis=[],
                        roadmap=[],
                    ),
                )

            parser = JsonOutputParser(pydantic_object=AnalysisResultV2)
            prompt = ChatPromptTemplate.from_template(ROADMAP_V2_PROMPT)
            chain = prompt | self.llm | parser
            parsed_result = chain.invoke(
                {
                    "user_specs": user_query_text,
                    "context": self._format_docs(retrieved_docs, content_limit=500),
                    "format_instructions": parser.get_format_instructions(),
                }
            )

            analysis_result = AnalysisResultV2.model_validate(parsed_result)

            recommended_jobs = [
                JobRecommendation(
                    id=self._normalize_doc_id(doc) or 0,
                    company=str(doc.metadata.get("company") or "미상"),
                    title=str(doc.metadata.get("position") or "미상"),
                )
                for doc in retrieved_docs
            ]

            return RoadmapResponseV2(
                user_name=user_info["username"],
                recommended_jobs=recommended_jobs,
                analysis_result=analysis_result,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("V2 roadmap 생성 실패: %s", exc)
            raise HTTPException(
                status_code=500, detail="V2 roadmap generation failed"
            ) from exc

    async def recommend_jobs_list(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> RecommendationListResponse:
        try:
            user_info = await self._fetch_user_info(user_id, session)
            user_query_text = self._build_user_query_text(
                user_info, include_career=True
            )

            retrieved_docs = self._similarity_search(user_query_text, limit=5)
            if not retrieved_docs:
                return RecommendationListResponse(
                    user_name=user_info["username"], recommendations=[]
                )

            parser = JsonOutputParser(pydantic_object=JobSummaryList)
            prompt = ChatPromptTemplate.from_template(RECOMMENDATION_PROMPT)
            chain = prompt | self.llm | parser

            parsed_result = chain.invoke(
                {
                    "user_specs": user_query_text,
                    "jobs_context": str(self._build_jobs_context(retrieved_docs)),
                    "format_instructions": parser.get_format_instructions(),
                }
            )

            validated_result = JobSummaryList.model_validate(parsed_result)
            return RecommendationListResponse(
                user_name=user_info["username"],
                recommendations=validated_result.jobs,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("추천 목록 생성 실패: %s", exc)
            raise HTTPException(
                status_code=500, detail="Job recommendation failed"
            ) from exc

    async def analyze_job_detail(
        self,
        job_id: int,
        user_id: int,
        session: AsyncSession,
    ) -> DetailedAnalysisResponse:
        try:
            user_info = await self._fetch_user_info(user_id, session)
            user_query_text = self._build_user_query_text(user_info)

            payload = self._fetch_job_payload(job_id)
            if not payload:
                raise HTTPException(
                    status_code=404, detail="해당 공고를 찾을 수 없습니다."
                )

            job_full_text = str(payload.get("full_text") or "")
            company = str(payload.get("company") or "미상")
            title = str(payload.get("position") or "미상")

            parser = JsonOutputParser(pydantic_object=DetailedAnalysisPayload)
            prompt = ChatPromptTemplate.from_template(DETAIL_ANALYSIS_PROMPT)
            chain = prompt | self.llm | parser
            parsed_result = chain.invoke(
                {
                    "user_specs": user_query_text,
                    "company": company,
                    "title": title,
                    "content": job_full_text,
                    "format_instructions": parser.get_format_instructions(),
                }
            )

            detail = DetailedAnalysisPayload.model_validate(parsed_result)
            return DetailedAnalysisResponse(
                job_title=title,
                company_name=company,
                current_score=detail.current_score,
                max_score=detail.max_score,
                analysis_summary=detail.analysis_summary,
                required_tech_stack=detail.required_tech_stack,
                action_plan=detail.action_plan,
                interview_tip=detail.interview_tip,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("상세 분석 생성 실패: %s", exc)
            raise HTTPException(
                status_code=500, detail="Detailed analysis failed"
            ) from exc

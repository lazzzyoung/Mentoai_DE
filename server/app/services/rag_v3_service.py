import asyncio
import logging
from typing import Any, cast

from fastapi import HTTPException

from server.app.core.config import COLLECTION_NAME, OPENAI_API_KEY, OPENAI_MODEL, QDRANT_URL
from server.app.repositories.user_repository import create_quick_user, fetch_user_info
from server.app.schemas.v3 import (
    DetailedAnalysisResponse,
    JobSummaryList,
    QuickLoginRequest,
    QuickLoginResponse,
    RecommendationListResponse,
    UserProfileSummary,
)

logger = logging.getLogger(__name__)

_resources: dict[str, Any] | None = None
_resources_lock = asyncio.Lock()


def _build_resources_sync() -> dict[str, Any]:
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_openai import ChatOpenAI
    from qdrant_client import AsyncQdrantClient

    logger.info("Loading Embedding Model...")
    embeddings = HuggingFaceEmbeddings(
        model_name="BM-K/KoSimCSE-roberta-multitask",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    logger.info("🔌 Connecting to Qdrant at %s...", QDRANT_URL)
    qdrant_client = AsyncQdrantClient(url=QDRANT_URL)

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    logger.info("🧠 Initializing OpenAI model: %s", OPENAI_MODEL)
    chat_openai = cast(Any, ChatOpenAI)
    llm = chat_openai(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=0.3,
        max_retries=2,
    )

    return {
        "embeddings": embeddings,
        "qdrant_client": qdrant_client,
        "llm": llm,
    }


async def _get_resources() -> dict[str, Any]:
    global _resources

    if _resources is not None:
        return _resources

    async with _resources_lock:
        if _resources is None:
            _resources = await asyncio.to_thread(_build_resources_sync)
        return _resources


def _coerce_job_id(raw_id: Any) -> int:
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str) and raw_id.isdigit():
        return int(raw_id)
    try:
        return int(str(raw_id))
    except (TypeError, ValueError):
        return 0


def _to_user_profile(user_info: dict[str, Any]) -> UserProfileSummary:
    desired_job = str(user_info.get("desired_job") or "미입력")

    raw_career_years = user_info.get("career_years")
    try:
        career_years = int(raw_career_years) if raw_career_years is not None else 0
    except (TypeError, ValueError):
        career_years = 0

    raw_skills = user_info.get("skills") or []
    skills = [str(skill).strip() for skill in raw_skills if str(skill).strip()]

    return UserProfileSummary(
        desired_job=desired_job,
        career_years=career_years,
        skills=skills,
    )


async def quick_login(data: QuickLoginRequest) -> QuickLoginResponse:
    try:
        user_id = await create_quick_user(
            user_name=data.user_name,
            desired_job=data.desired_job,
            career_years=data.career_years,
            skills=data.skills,
        )
        user_info = await fetch_user_info(user_id)

        user_name = str(user_info.get("username") or data.user_name)
        return QuickLoginResponse(
            user_id=user_id,
            user_name=user_name,
            user_profile=_to_user_profile(user_info),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("V3 Quick Login Error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="로그인 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


def _build_user_query_text(user_profile: UserProfileSummary) -> str:
    skills_text = ", ".join(user_profile.skills) if user_profile.skills else "없음"
    return (
        f"희망직무: {user_profile.desired_job}, "
        f"보유기술: {skills_text}, "
        f"경력: {user_profile.career_years}년"
    )


async def recommend_jobs_list(user_id: int) -> RecommendationListResponse:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        user_query_text = _build_user_query_text(user_profile)

        resources = await _get_resources()
        embeddings = resources["embeddings"]
        qdrant_client = resources["qdrant_client"]
        llm = resources["llm"]

        query_vector = await embeddings.aembed_query(user_query_text)
        search_result = await qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=5,
            with_payload=True,
            with_vectors=False,
        )

        points = search_result.points or []
        if not points:
            return RecommendationListResponse(
                user_id=user_id,
                user_name=user_info["username"],
                user_profile=user_profile,
                recommendations=[],
            )

        jobs_context = []
        for point in points:
            payload = point.payload or {}
            jobs_context.append(
                {
                    "job_id": _coerce_job_id(point.id),
                    "company": payload.get("company", "미상"),
                    "title": payload.get("position", "미상"),
                    "content": cast(str, payload.get("full_text", ""))[:300],
                }
            )

        parser = JsonOutputParser(pydantic_object=JobSummaryList)
        template = """
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
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm | parser

        result = await chain.ainvoke(
            {
                "user_specs": user_query_text,
                "jobs_context": str(jobs_context),
                "format_instructions": parser.get_format_instructions(),
            }
        )

        scored_jobs = result.get("jobs", []) if isinstance(result, dict) else []
        return RecommendationListResponse(
            user_id=user_id,
            user_name=user_info["username"],
            user_profile=user_profile,
            recommendations=scored_jobs,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("V3 List Error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="추천 결과를 준비하는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def analyze_job_detail(job_id: int, user_id: int) -> dict[str, Any]:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        user_query_text = _build_user_query_text(user_profile)

        resources = await _get_resources()
        qdrant_client = resources["qdrant_client"]
        llm = resources["llm"]

        points = await qdrant_client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[job_id],
            with_payload=True,
        )
        if not points:
            raise HTTPException(404, "해당 공고를 찾을 수 없습니다.")

        payload = points[0].payload or {}
        job_full_text = payload.get("full_text", "")
        company = payload.get("company", "미상")
        title = payload.get("position", "미상")

        parser = JsonOutputParser(pydantic_object=DetailedAnalysisResponse)
        template = """
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
        prompt = ChatPromptTemplate.from_template(template)
        chain = prompt | llm | parser

        analysis_result = await chain.ainvoke(
            {
                "user_specs": user_query_text,
                "company": company,
                "title": title,
                "content": job_full_text,
                "format_instructions": parser.get_format_instructions(),
            }
        )

        if not isinstance(analysis_result, dict):
            analysis_result = {}

        analysis_result["job_title"] = title
        analysis_result["company_name"] = company
        return analysis_result
    except HTTPException:
        raise
    except Exception as error:
        logger.error("V3 Detail Error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="공고 분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def close_resources() -> None:
    global _resources

    if _resources is None:
        return

    async with _resources_lock:
        if _resources is None:
            return

        qdrant_client = _resources.get("qdrant_client")
        if qdrant_client is not None:
            await qdrant_client.close()
        _resources = None

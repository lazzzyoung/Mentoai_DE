import os
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold
from langchain_huggingface import HuggingFaceEmbeddings
from qdrant_client import QdrantClient
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MentoAI RAG Server")

# --- 설정 ---
DB_URL = os.getenv("DATABASE_URL", "postgresql://airflow:airflow@postgres:5432/mentoai")
QDRANT_HOST = os.getenv("QDRANT_HOST", "mentoai-qdrant")
QDRANT_URL = f"http://{QDRANT_HOST}:6333"
COLLECTION_NAME = "career_jobs"

# --- AI 모델 초기화 ---
logger.info("Loading Embedding Model...")
embeddings = HuggingFaceEmbeddings(
    model_name="BM-K/KoSimCSE-roberta-multitask",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

logger.info(f"🔌 Connecting to Qdrant at {QDRANT_URL}...")
client = QdrantClient(url=QDRANT_URL)

# 검색용 Store
vector_store = QdrantVectorStore(
    client=client,
    collection_name=COLLECTION_NAME,
    embedding=embeddings,
    content_payload_key="full_text",
    metadata_payload_key=None
)

logger.info("🧠 Initializing Google Gemini 3 Flash Preview...")
llm = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview", 
    google_api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.3, 
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    },
)

def fetch_user_info(user_id: int):
    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT u.username, s.desired_job, s.career_years, s.skills FROM user_specs s JOIN users u ON s.user_id = u.id WHERE s.user_id = %s", (user_id,))
        user_info = cur.fetchone()
        if not user_info: raise HTTPException(404, "User not found")
        return user_info
    finally:
        if conn: conn.close()


class UserSpecResponse(BaseModel):
    user_id: int
    desired_job: str
    career_years: int
    education: str
    skills: List[str]
    certificates: List[str]

# [V1 모델]
class RoadmapResponseV1(BaseModel):
    user_name: str
    recommended_jobs: List[str]
    analysis_result: str

# [V2 모델]
class JobRecommendation(BaseModel):
    id: int
    company: str
    title: str

class GapItem(BaseModel):
    skill: str
    score_impact: int
    action_guide: str

class RoadmapStep(BaseModel):
    step_name: str
    description: str

class AnalysisResultV2(BaseModel):
    current_score: int
    summary: str
    gap_analysis: List[GapItem]
    roadmap: List[RoadmapStep]

class RoadmapResponseV2(BaseModel):
    user_name: str
    recommended_jobs: List[JobRecommendation]
    analysis_result: AnalysisResultV2

# [V3 모델] - 목록 조회용
class JobSummary(BaseModel):
    job_id: int
    company: str
    title: str
    match_score: int = Field(description="적합도 점수 (60~100)")
    max_score: int = Field(default=100, description="만점 기준")
    reason: str = Field(description="추천 이유 한 줄 요약")

class JobSummaryList(BaseModel):
    jobs: List[JobSummary]

class RecommendationListResponse(BaseModel):
    user_name: str
    recommendations: List[JobSummary]

# [V3 모델] - 상세 조회용
class ActionItem(BaseModel):
    category: str
    item_name: str
    description: str
    expected_score_up: int

class DetailedAnalysisResponse(BaseModel):
    job_title: str
    company_name: str
    current_score: int
    max_score: int = 100
    analysis_summary: str
    required_tech_stack: List[str]
    action_plan: List[ActionItem]
    interview_tip: str


# =========================================================
# 기본 엔드포인트
# =========================================================

@app.get("/")
def health_check():
    return {"status": "ok", "message": "MentoAI Brain is running with Gemini"}

@app.get("/api/v1/test/gemini")
def test_gemini_connection(prompt: str = "안녕"):
    try:
        response = llm.invoke(prompt)
        return {"gemini_response": response.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/users/{user_id}/specs", response_model=UserSpecResponse)
def get_user_specs(user_id: int):
    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM user_specs WHERE user_id = %s", (user_id,))
        result = cur.fetchone()
        if not result: raise HTTPException(404, "User not found")
        return result
    finally:
        if conn: conn.close()


# =========================================================
# [V1] 기존 Markdown 로드맵
# =========================================================
@app.post("/api/v1/curation/roadmap/{user_id}", response_model=RoadmapResponseV1)
def generate_career_roadmap_v1(user_id: int):
    try:
        user_info = fetch_user_info(user_id)
        user_query_text = f"희망직무: {user_info['desired_job']}, 보유기술: {', '.join(user_info['skills'] or [])}"
        
        retrieved_docs = vector_store.similarity_search(user_query_text, k=3)
        if not retrieved_docs:
             return RoadmapResponseV1(user_name=user_info['username'], recommended_jobs=[], analysis_result="공고 없음")

        template = """
        [사용자] {user_specs}
        [채용공고] {context}
        합격을 위한 전략적 로드맵을 Markdown으로 작성해주세요.
        """
        prompt = ChatPromptTemplate.from_template(template)
        formatted_context = "\n".join([f"기업: {d.metadata.get('company')}\n제목: {d.metadata.get('position')}\n내용: {d.page_content[:300]}" for d in retrieved_docs])
        
        chain = prompt | llm | StrOutputParser()
        analysis_result = chain.invoke({"user_specs": user_query_text, "context": formatted_context})

        return RoadmapResponseV1(
            user_name=user_info['username'],
            recommended_jobs=[doc.metadata.get('position') or "미상" for doc in retrieved_docs],
            analysis_result=analysis_result
        )
    except Exception as e:
        logger.error(f"V1 Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# [V2] JSON 구조화 로드맵
# =========================================================
@app.post("/api/v2/curation/roadmap/{user_id}", response_model=RoadmapResponseV2)
def generate_career_roadmap_v2(user_id: int):
    try:
        user_info = fetch_user_info(user_id)
        user_query_text = f"희망직무: {user_info['desired_job']}, 보유기술: {', '.join(user_info['skills'] or [])}"
        
        retrieved_docs = vector_store.similarity_search(user_query_text, k=3)
        if not retrieved_docs:
             empty = AnalysisResultV2(current_score=0, summary="공고 없음", gap_analysis=[], roadmap=[])
             return RoadmapResponseV2(user_name=user_info['username'], recommended_jobs=[], analysis_result=empty)

        parser = JsonOutputParser(pydantic_object=AnalysisResultV2)
        template = """
        사용자 스펙과 공고를 비교하여 JSON으로 응답하세요. 마크다운 사용 금지.
        [프로필] {user_specs}
        [공고] {context}
        {format_instructions}
        """
        prompt = ChatPromptTemplate.from_template(template)
        formatted_context = "\n".join([f"기업: {d.metadata.get('company')}\n제목: {d.metadata.get('position')}\n내용: {d.page_content[:500]}" for d in retrieved_docs])
        
        chain = prompt | llm | parser
        analysis_result_dict = chain.invoke({
            "user_specs": user_query_text, 
            "context": formatted_context,
            "format_instructions": parser.get_format_instructions()
        })
        
        recommended_jobs = [
            JobRecommendation(
                id=d.metadata.get('id') or d.metadata.get('_id') or 0,
                company=d.metadata.get('company') or "미상",
                title=d.metadata.get('position') or "미상"
            ) for d in retrieved_docs
        ]

        return RoadmapResponseV2(
            user_name=user_info['username'],
            recommended_jobs=recommended_jobs,
            analysis_result=analysis_result_dict
        )
    except Exception as e:
        logger.error(f"V2 Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================
# [V3 - API 1] 기업 목록 및 점수 조회
# =========================================================
@app.post("/api/v3/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
def recommend_jobs_list(user_id: int):
    try:
        user_info = fetch_user_info(user_id)
        user_query_text = f"희망직무: {user_info['desired_job']}, 보유기술: {', '.join(user_info['skills'] or [])}, 경력: {user_info['career_years']}년"
        
        retrieved_docs = vector_store.similarity_search(user_query_text, k=5)
        
        if not retrieved_docs:
            return RecommendationListResponse(user_name=user_info['username'], recommendations=[])

        jobs_context = []
        for doc in retrieved_docs:
            doc_id = doc.metadata.get('id') or doc.metadata.get('_id')
            
            # 기본값 설정
            company = "미상"
            title = "미상"
            content = doc.page_content

            if doc_id:
                try:
                    
                    points = client.retrieve(
                        collection_name=COLLECTION_NAME,
                        ids=[doc_id],
                        with_payload=True
                    )
                    if points:
                        payload = points[0].payload
                        company = payload.get('company', "미상")
                        title = payload.get('position', "미상")
                        content = payload.get('full_text', content)
                except Exception as e:
                    logger.warning(f"Metadata fetch failed for ID {doc_id}: {e}")

            jobs_context.append({
                "job_id": doc_id,
                "company": company,
                "title": title,
                "content": content[:300] 
            })

        # LLM 채점
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
        
        # 결과 파싱
        result = chain.invoke({
            "user_specs": user_query_text,
            "jobs_context": str(jobs_context),
            "format_instructions": parser.get_format_instructions()
        })
        
        scored_jobs = result.get("jobs", [])
        
        return RecommendationListResponse(
            user_name=user_info['username'],
            recommendations=scored_jobs
        )

    except Exception as e:
        logger.error(f"V3 List Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# [V3 - API 2] 상세 컨설팅
# =========================================================
@app.post("/api/v3/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse)
def analyze_job_detail(job_id: int, user_id: int):
    try:
        user_info = fetch_user_info(user_id)
        user_query_text = f"희망직무: {user_info['desired_job']}, 보유기술: {', '.join(user_info['skills'] or [])}"
        
        # 상세 조회
        points = client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[job_id],
            with_payload=True
        )
        
        if not points:
            raise HTTPException(404, "해당 공고를 찾을 수 없습니다.")
            
        job_payload = points[0].payload
        job_full_text = job_payload.get('full_text', '')
        company = job_payload.get('company', "미상")
        title = job_payload.get('position', "미상")
        
        # LLM 상세 컨설팅
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
        
        analysis_result = chain.invoke({
            "user_specs": user_query_text,
            "company": company,
            "title": title,
            "content": job_full_text,
            "format_instructions": parser.get_format_instructions()
        })
        
        # 메타데이터 보정
        analysis_result['job_title'] = title
        analysis_result['company_name'] = company
        
        return analysis_result

    except Exception as e:
        logger.error(f"V3 Detail Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
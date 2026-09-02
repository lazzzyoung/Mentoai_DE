import logging
from typing import Any

from fastapi import HTTPException

from mentoai.ai.gemini import generate_structured
from mentoai.ai.schemas import DetailedAnalysisResponse
from mentoai.ai.users import build_profile_text, fetch_user_info
from mentoai.config import get_settings
from mentoai.db.pool import execute, fetchrow

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """당신은 IT 대기업 및 유니콘 스타트업의 시니어 테크 리드(Tech Lead)이자 채용 최종 결정권자입니다.
지원자의 이력서와 공고를 비교 분석하여, 당장 실천 가능한 '합격 치트키' 수준의 전략을 수립하세요.

[지원자 프로필] {user_specs}
[목표 공고] {company} / {title}
[공고 내용]
{content}

**작성 지침 (Deep Dive):**

1. current_score (냉철한 평가): 50~85점 사이로 책정하고, 왜 감점되었는지를 액션 플랜에 녹여내세요.

2. required_tech_stack (핵심 파악): 공고에 나열된 기술 중, 지원자가 없으면 서류 광탈할 Critical Stack 3~5가지만 엄선하세요.

3. action_plan (초구체적 실행 가이드):
   - 추상적인 조언(예: "Kubernetes 공부하기")은 절대 금지입니다. How-to를 포함한 시나리오를 제시하세요.
   - 예시: "현재 보유한 FastAPI 프로젝트를 Docker 이미지로 빌드하고 AWS EKS에 배포하는 실습을 하세요. Terraform으로 인프라를 프로비저닝하여 IaC 경험을 포트폴리오에 추가해야 합니다."

4. interview_tip (면접관의 시선): 해당 회사의 도메인과 기술 스택을 결합한 예상 질문과 모범 답안 키워드를 알려주세요.
"""

CACHE_HIT_SQL = """
SELECT response FROM analysis_cache
WHERE job_id = $1 AND user_id = $2 AND model = $3
"""

CACHE_UPSERT_SQL = """
INSERT INTO analysis_cache (job_id, user_id, model, response)
VALUES ($1, $2, $3, $4)
ON CONFLICT (job_id, user_id, model)
DO UPDATE SET response = EXCLUDED.response, created_at = now()
"""


async def analyze_job(job_id: int, user_id: int) -> dict[str, Any]:
    """공고 상세 커리어 컨설팅. (job_id, user_id, model) 캐시로 Gemini 호출은 1회만."""
    settings = get_settings()
    try:
        user = await fetch_user_info(user_id)
        job = await fetchrow(
            """
            SELECT id, company, position, full_text
            FROM silver.jobs WHERE id = $1
            """,
            job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="해당 공고를 찾을 수 없습니다.")

        cached = await fetchrow(CACHE_HIT_SQL, job_id, user_id, settings.gemini_model)
        if cached:
            return cached["response"]

        prompt = ANALYSIS_PROMPT.format(
            user_specs=build_profile_text(user),
            company=job["company"] or "미상",
            title=job["position"] or "미상",
            content=job["full_text"],
        )
        result = await generate_structured(prompt, DetailedAnalysisResponse)
        payload = result.model_dump()

        await execute(
            CACHE_UPSERT_SQL, job_id, user_id, settings.gemini_model, payload
        )
        return payload
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("상세 분석 실패 (job_id=%s, user_id=%s)", job_id, user_id)
        raise HTTPException(status_code=500, detail=str(error)) from error

import logging

from fastapi import HTTPException

from mentoai.ai.embeddings import embed_query
from mentoai.ai.schemas import JobSummary, RecommendationListResponse
from mentoai.ai.scoring import build_reason, similarity_to_score, skill_overlap
from mentoai.ai.users import build_profile_text, fetch_user_info
from mentoai.config import get_settings
from mentoai.db.pool import fetch

logger = logging.getLogger(__name__)

SEARCH_SQL = """
SELECT j.id, j.source, j.company, j.position, j.skill_tags, j.annual_from, j.annual_to,
       j.is_newbie, j.location,
       1 - (e.embedding <=> $1) AS similarity
FROM silver.job_embeddings e
JOIN silver.jobs j ON j.id = e.job_id
ORDER BY e.embedding <=> $1
LIMIT $2
"""


def career_label(annual_from: int | None, annual_to: int | None, is_newbie: bool | None) -> str | None:
    if is_newbie:
        return "신입 가능"
    if annual_from is not None:
        if (annual_to or 0) >= 99:  # Wanted의 '상한 없음'은 100으로 온다
            return f"경력 {annual_from}년 이상"
        return f"경력 {annual_from}~{annual_to or annual_from}년"
    return None


async def recommend_jobs(user_id: int) -> RecommendationListResponse:
    """벡터 유사도 + 휴리스틱으로 추천. LLM 호출/비용 없이 즉시 응답한다."""
    try:
        user = await fetch_user_info(user_id)
        query_vector = await embed_query(build_profile_text(user))
        rows = await fetch(SEARCH_SQL, query_vector, get_settings().recommend_top_k)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("추천 조회 실패 (user_id=%s)", user_id)
        raise HTTPException(status_code=500, detail=str(error)) from error

    user_skills = list(user["skills"] or [])
    career_years = user["career_years"]
    recommendations = [
        JobSummary(
            job_id=row["id"],
            company=row["company"] or "미상",
            title=row["position"] or "미상",
            source=row["source"],
            career=career_label(row["annual_from"], row["annual_to"], row["is_newbie"]),
            location=row["location"],
            skills=list(row["skill_tags"] or [])[:4],
            matched_skills=skill_overlap(user_skills, list(row["skill_tags"] or [])),
            match_score=similarity_to_score(row["similarity"]),
            reason=build_reason(user_skills, career_years, dict(row)),
        )
        for row in rows
    ]
    return RecommendationListResponse(
        user_name=user["username"], recommendations=recommendations
    )

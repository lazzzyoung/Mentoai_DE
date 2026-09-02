from typing import Any

from fastapi import APIRouter

from mentoai.ai import analyzer as analyzer_service
from mentoai.ai import recommend as recommend_service
from mentoai.ai import users as users_service
from mentoai.ai.schemas import (
    DetailedAnalysisResponse,
    RecommendationListResponse,
    UserSummary,
)

router = APIRouter(tags=["v1"])


@router.get("/api/v1/users", response_model=list[UserSummary])
async def list_users() -> list[dict[str, Any]]:
    return await users_service.list_users()


@router.post("/api/v1/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
async def recommend_jobs(user_id: int) -> RecommendationListResponse:
    return await recommend_service.recommend_jobs(user_id)


@router.post("/api/v1/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse)
async def analyze_job(job_id: int, user_id: int) -> dict[str, Any]:
    return await analyzer_service.analyze_job(job_id, user_id)

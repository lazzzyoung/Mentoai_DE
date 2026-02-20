from typing import Any

from fastapi import APIRouter, Query

from server.app.schemas.v3 import (
    DetailedAnalysisResponse,
    QuickLoginRequest,
    QuickLoginResponse,
    RecommendationListResponse,
)
from server.app.services import rag_v3_service

router = APIRouter(tags=["v3"])


@router.post("/api/v3/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
async def recommend_jobs_list(
    user_id: int,
    limit: int | None = Query(default=None, ge=1, le=200),
) -> RecommendationListResponse:
    return await rag_v3_service.recommend_jobs_list(user_id, limit=limit)


@router.post("/api/v3/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse)
async def analyze_job_detail(job_id: int, user_id: int) -> dict[str, Any]:
    return await rag_v3_service.analyze_job_detail(job_id, user_id)


@router.post("/api/v3/auth/quick-login", response_model=QuickLoginResponse)
async def quick_login(payload: QuickLoginRequest) -> QuickLoginResponse:
    return await rag_v3_service.quick_login(payload)

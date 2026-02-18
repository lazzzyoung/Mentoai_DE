from fastapi import APIRouter

from server.app.schemas.v3 import DetailedAnalysisResponse, RecommendationListResponse
from server.app.services import rag_v3_service

router = APIRouter(tags=["v3"])


@router.post("/api/v3/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
def recommend_jobs_list(user_id: int) -> RecommendationListResponse:
    return rag_v3_service.recommend_jobs_list(user_id)


@router.post("/api/v3/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse)
def analyze_job_detail(job_id: int, user_id: int) -> dict:
    return rag_v3_service.analyze_job_detail(job_id, user_id)

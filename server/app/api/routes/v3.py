from fastapi import APIRouter, Depends

from server.app.api.deps import get_rag_service
from server.app.schemas.v3 import DetailedAnalysisResponse, RecommendationListResponse
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v3", tags=["v3"])


@router.post("/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
def recommend_jobs_list(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
) -> RecommendationListResponse:
    return service.recommend_jobs_list(user_id)


@router.post(
    "/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse
)
def analyze_job_detail(
    job_id: int,
    user_id: int,
    service: RAGService = Depends(get_rag_service),
) -> DetailedAnalysisResponse:
    return service.analyze_job_detail(job_id, user_id)

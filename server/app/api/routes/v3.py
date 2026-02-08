from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.api.deps import get_rag_service
from server.app.db.session import get_async_session
from server.app.schemas.v3 import DetailedAnalysisResponse, RecommendationListResponse
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v3", tags=["v3"])


@router.post("/jobs/recommend/{user_id}", response_model=RecommendationListResponse)
async def recommend_jobs_list(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
    session: AsyncSession = Depends(get_async_session),
) -> RecommendationListResponse:
    return await service.recommend_jobs_list(user_id, session)


@router.post(
    "/jobs/{job_id}/analyze/{user_id}", response_model=DetailedAnalysisResponse
)
async def analyze_job_detail(
    job_id: int,
    user_id: int,
    service: RAGService = Depends(get_rag_service),
    session: AsyncSession = Depends(get_async_session),
) -> DetailedAnalysisResponse:
    return await service.analyze_job_detail(job_id, user_id, session)

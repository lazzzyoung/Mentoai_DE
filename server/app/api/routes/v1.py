from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.api.deps import get_rag_service
from server.app.db.session import get_async_session
from server.app.schemas.user import UserSpecResponse
from server.app.schemas.v1 import (
    DetailedAnalysisResponse,
    RecommendationListResponse,
    RoadmapResponse,
)
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/test/gemini")
async def test_gemini_connection(
    prompt: str = "안녕",
    service: RAGService = Depends(get_rag_service),
) -> dict[str, str]:
    return await service.test_gemini_connection(prompt)


@router.get("/users/{user_id}/specs", response_model=UserSpecResponse)
async def get_user_specs(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    return await service.get_user_specs(user_id, session)


@router.post("/curation/roadmap/{user_id}", response_model=RoadmapResponse)
async def generate_career_roadmap(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
    session: AsyncSession = Depends(get_async_session),
) -> RoadmapResponse:
    return await service.generate_career_roadmap(user_id, session)


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

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.api.deps import get_rag_service
from server.app.db.session import get_async_session
from server.app.schemas.v2 import RoadmapResponseV2
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.post("/curation/roadmap/{user_id}", response_model=RoadmapResponseV2)
async def generate_career_roadmap_v2(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
    session: AsyncSession = Depends(get_async_session),
) -> RoadmapResponseV2:
    return await service.generate_career_roadmap_v2(user_id, session)

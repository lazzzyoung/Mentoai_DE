from fastapi import APIRouter, Depends

from server.app.api.deps import get_rag_service
from server.app.schemas.v2 import RoadmapResponseV2
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v2", tags=["v2"])


@router.post("/curation/roadmap/{user_id}", response_model=RoadmapResponseV2)
def generate_career_roadmap_v2(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
) -> RoadmapResponseV2:
    return service.generate_career_roadmap_v2(user_id)

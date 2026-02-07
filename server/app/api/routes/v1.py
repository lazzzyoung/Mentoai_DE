from fastapi import APIRouter, Depends

from server.app.api.deps import get_rag_service
from server.app.schemas.user import UserSpecResponse
from server.app.schemas.v1 import RoadmapResponseV1
from server.app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/test/gemini")
def test_gemini_connection(
    prompt: str = "안녕",
    service: RAGService = Depends(get_rag_service),
) -> dict[str, str]:
    return service.test_gemini_connection(prompt)


@router.get("/users/{user_id}/specs", response_model=UserSpecResponse)
def get_user_specs(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
) -> dict:
    return service.get_user_specs(user_id)


@router.post("/curation/roadmap/{user_id}", response_model=RoadmapResponseV1)
def generate_career_roadmap_v1(
    user_id: int,
    service: RAGService = Depends(get_rag_service),
) -> RoadmapResponseV1:
    return service.generate_career_roadmap_v1(user_id)

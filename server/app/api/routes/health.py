from fastapi import APIRouter

router = APIRouter(tags=["health"])
HEALTH_PAYLOAD = {"status": "ok", "message": "MentoAI server is running"}


@router.get("/health")
def health_check() -> dict[str, str]:
    return HEALTH_PAYLOAD

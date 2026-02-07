from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "MentoAI Brain is running with Gemini"}

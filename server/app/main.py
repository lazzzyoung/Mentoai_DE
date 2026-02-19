import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.app.api.routes.v3 import router as v3_router
from server.app.repositories.user_repository import close_pool
from server.app.services.rag_v3_service import close_resources

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_resources()
    await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server", lifespan=lifespan)

    @app.get("/")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "message": "MentoAI Brain is running with Gemini"}

    app.include_router(v3_router)
    return app


app = create_app()

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from server.app.api.routes.v3 import router as v3_router
from server.app.repositories.user_repository import close_pool
from server.app.services.rag_v3_service import close_resources

logging.basicConfig(level=logging.INFO)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_resources()
    await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server", lifespan=lifespan)
    allowed_hosts = [
        host.strip() for host in os.getenv("ALLOWED_HOSTS", "").split(",") if host.strip()
    ]
    if allowed_hosts:
        app.add_middleware(cast(Any, TrustedHostMiddleware), allowed_hosts=allowed_hosts)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def root_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "home.html")

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "message": "MentoAI service is running"}

    @app.get("/jobs")
    async def jobs_home() -> FileResponse:
        return FileResponse(STATIC_DIR / "home.html")

    @app.get("/jobs/recommend")
    async def jobs_recommend_page() -> FileResponse:
        # AI 기반 공고 추천 화면 (v3 API1 중심 화면)
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/jobs/detail")
    async def jobs_detail_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "detail.html")

    @app.get("/jobs/detail/{job_id}")
    async def jobs_detail_page_by_id(job_id: int) -> FileResponse:
        # 특정 공고 상세 분석 화면 (v3 API2 중심 화면)
        return FileResponse(STATIC_DIR / "detail.html")

    app.include_router(v3_router)
    return app


app = create_app()

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mentoai.api.admin import router as admin_router
from mentoai.api.routes import router as api_router
from mentoai.api.scheduler import start_scheduler
from mentoai.db.pool import close_pool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler = await start_scheduler()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI", version="1.0.0", lifespan=lifespan)
    app.include_router(api_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin")
    async def admin_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "admin.html")

    # 모놀리식 UI: 빌드 도구 없는 정적 페이지를 같은 프로세스에서 서빙한다
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
    return app


app = create_app()

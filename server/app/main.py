import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.app.api.routes import health, v1, web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server")
    static_dir = BASE_DIR / "static"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        logger.warning("Static directory not found: %s", static_dir)

    app.include_router(health.router)
    app.include_router(v1.router)
    app.include_router(web.router)

    return app


app = create_app()

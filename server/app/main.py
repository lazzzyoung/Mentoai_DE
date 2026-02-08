import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.app.api.routes import health, v1, web

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server")

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    app.include_router(health.router)
    app.include_router(v1.router)
    app.include_router(web.router)

    return app


app = create_app()

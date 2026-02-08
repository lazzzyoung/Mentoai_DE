import logging

from fastapi import FastAPI

from server.app.api.routes import health, v1

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server")
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()

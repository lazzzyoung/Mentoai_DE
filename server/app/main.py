import logging

from fastapi import FastAPI

from server.app.api.routes.v3 import router as v3_router

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(title="MentoAI RAG Server")

    @app.get("/")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "message": "MentoAI Brain is running with Gemini"}

    app.include_router(v3_router)
    return app


app = create_app()

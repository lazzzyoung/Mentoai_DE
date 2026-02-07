from functools import lru_cache

from server.app.core.config import get_settings
from server.app.services.rag_service import RAGService


@lru_cache
def get_rag_service() -> RAGService:
    return RAGService(get_settings())

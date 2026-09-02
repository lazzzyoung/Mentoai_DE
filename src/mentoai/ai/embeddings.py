import asyncio
import logging
import threading
from typing import Any

import numpy as np

from mentoai.config import get_settings

logger = logging.getLogger(__name__)

GEMINI_BATCH_SIZE = 100

_fastembed_model: Any | None = None
_model_lock = threading.Lock()


def embed_prefixes(model_name: str) -> tuple[str, str]:
    """(query_prefix, document_prefix). E5 계열만 접두어가 필요하다."""
    lowered = model_name.lower()
    if "e5" in lowered:
        return ("query: ", "passage: ")
    return ("", "")


def _get_fastembed_sync() -> Any:
    global _fastembed_model
    if _fastembed_model is None:
        with _model_lock:
            if _fastembed_model is None:
                from fastembed import TextEmbedding

                settings = get_settings()
                logger.info("임베딩 모델 로딩: %s", settings.embedding_model)
                _fastembed_model = TextEmbedding(
                    model_name=settings.embedding_model,
                    cache_dir=settings.embedding_cache_dir,
                )
    return _fastembed_model


def _fastembed_documents_sync(texts: list[str]) -> list[np.ndarray]:
    model = _get_fastembed_sync()
    _, prefix = embed_prefixes(get_settings().embedding_model)
    return [np.asarray(v) for v in model.embed([f"{prefix}{t}" for t in texts])]


def _fastembed_query_sync(text: str) -> np.ndarray:
    model = _get_fastembed_sync()
    prefix, _ = embed_prefixes(get_settings().embedding_model)
    return np.asarray(next(iter(model.embed([f"{prefix}{text}"]))))


async def _gemini_embed(contents: list[str], task_type: str) -> list[np.ndarray]:
    """gemini-embedding-001. output_dimensionality로 컬럼 차원(1024)에 맞춘다."""
    from mentoai.ai.gemini import get_client

    settings = get_settings()
    client = await get_client()
    vectors: list[np.ndarray] = []
    for start in range(0, len(contents), GEMINI_BATCH_SIZE):
        chunk = contents[start : start + GEMINI_BATCH_SIZE]
        response = await client.aio.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=chunk,
            config={
                "task_type": task_type,
                "output_dimensionality": settings.embedding_dim,
            },
        )
        vectors.extend(np.asarray(e.value) for e in response.embeddings)
    return vectors


async def embed_documents(texts: list[str]) -> list[np.ndarray]:
    if get_settings().embedding_provider == "gemini":
        return await _gemini_embed(texts, "RETRIEVAL_DOCUMENT")
    return await asyncio.to_thread(_fastembed_documents_sync, texts)


async def embed_query(text: str) -> np.ndarray:
    if get_settings().embedding_provider == "gemini":
        return (await _gemini_embed([text], "RETRIEVAL_QUERY"))[0]
    return await asyncio.to_thread(_fastembed_query_sync, text)


def model_key() -> str:
    """DB model 컬럼에 저장하는 식별자. 공급자까지 구분해 모델 전환 감지에 쓴다."""
    settings = get_settings()
    model = (
        settings.gemini_embedding_model
        if settings.embedding_provider == "gemini"
        else settings.embedding_model
    )
    return f"{settings.embedding_provider}:{model}"


def reset_model() -> None:
    """설정 변경 후 싱글턴을 버린다 (임베딩 모델 전환용)."""
    global _fastembed_model
    _fastembed_model = None

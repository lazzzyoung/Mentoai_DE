from __future__ import annotations

import hashlib
import importlib
import logging
import math
from threading import Lock
from typing import Any

from server.app.core.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_MODEL_UNAVAILABLE = object()
_model: Any = None
_model_lock = Lock()


def _hash_embedding(text: str, dim: int = 128) -> list[float]:
    vector = [0.0] * dim
    tokens = (text or "").split()
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        vector[idx] += 1.0

    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _load_model() -> None:
    """임베딩 모델을 1회만 로드하고 실패 시 fallback 상태로 고정한다."""
    global _model

    if _model is _MODEL_UNAVAILABLE or _model is not None:
        return

    with _model_lock:
        if _model is _MODEL_UNAVAILABLE or _model is not None:
            return

        try:
            sentence_transformers = importlib.import_module("sentence_transformers")
            model_class = sentence_transformers.SentenceTransformer
            _model = model_class(EMBEDDING_MODEL, device="cpu")
            logger.info("Embedding model loaded: %s", EMBEDDING_MODEL)
        except ModuleNotFoundError:
            logger.warning("sentence_transformers 패키지가 없어 hash fallback 임베딩을 사용합니다.")
            _model = _MODEL_UNAVAILABLE
        except Exception as error:  # pragma: no cover - fallback path
            logger.warning("Embedding model load failed, using hash fallback: %s", error)
            _model = _MODEL_UNAVAILABLE


async def embed_text(text: str) -> list[float]:
    _load_model()
    if _model is _MODEL_UNAVAILABLE or _model is None:
        return _hash_embedding(text)

    vector = _model.encode(text or "", normalize_embeddings=True)
    return [float(value) for value in vector.tolist()]

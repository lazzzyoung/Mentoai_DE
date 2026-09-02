import asyncio
from types import SimpleNamespace

import numpy as np

from mentoai.ai import embeddings


def _stub_settings(**overrides):
    base = {
        "embedding_provider": "fastembed",
        "embedding_model": "intfloat/multilingual-e5-large",
        "embedding_cache_dir": ".models",
        "gemini_embedding_model": "gemini-embedding-001",
        "embedding_dim": 1024,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_fastembed_query_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(embeddings, "get_settings", lambda: _stub_settings())

    def fake_query_sync(text: str) -> np.ndarray:
        assert text == "데이터 엔지니어"  # 원문 그대로 전달 (접두어는 내부 처리)
        return np.zeros(1024)

    monkeypatch.setattr(embeddings, "_fastembed_query_sync", fake_query_sync)
    vector = asyncio.run(embeddings.embed_query("데이터 엔지니어"))
    assert vector.shape == (1024,)


def test_gemini_query_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(
        embeddings, "get_settings", lambda: _stub_settings(embedding_provider="gemini")
    )
    tasks: list[str] = []

    async def fake_gemini(contents: list[str], task_type: str) -> list[np.ndarray]:
        tasks.append(task_type)
        return [np.full(1024, 0.5) for _ in contents]

    monkeypatch.setattr(embeddings, "_gemini_embed", fake_gemini)
    vector = asyncio.run(embeddings.embed_query("데이터 엔지니어"))
    assert vector.shape == (1024,)
    assert tasks == ["RETRIEVAL_QUERY"]  # 쿼리/문서 task_type 분리 확인


def test_gemini_documents_batching(monkeypatch) -> None:
    """_gemini_embed 실제 경로: 배치 100 제한 + task_type/차원 설정 확인."""
    monkeypatch.setattr(
        embeddings, "get_settings", lambda: _stub_settings(embedding_provider="gemini")
    )
    calls: list[tuple[int, dict]] = []

    class FakeEmbedding:
        def __init__(self) -> None:
            self.value = [0.1] * 1024

    class FakeResponse:
        def __init__(self, count: int) -> None:
            self.embeddings = [FakeEmbedding() for _ in range(count)]

    class FakeModels:
        async def embed_content(self, *, contents: list, config: dict, **_: object):
            calls.append((len(contents), dict(config)))
            return FakeResponse(len(contents))

    class FakeClient:
        aio = SimpleNamespace(models=FakeModels())

    async def fake_get_client() -> FakeClient:
        return FakeClient()

    monkeypatch.setattr("mentoai.ai.gemini.get_client", fake_get_client)

    vectors = asyncio.run(embeddings.embed_documents(["공고"] * 250))

    assert len(vectors) == 250
    assert [size for size, _ in calls] == [100, 100, 50]  # 배치 100 제한 준수
    assert all(config["task_type"] == "RETRIEVAL_DOCUMENT" for _, config in calls)
    assert all(config["output_dimensionality"] == 1024 for _, config in calls)

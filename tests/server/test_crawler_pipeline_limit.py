import pytest

from server.app.services import crawler_pipeline


class _DummySession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def __enter__(self) -> "_DummySession":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


@pytest.mark.anyio
async def test_run_crawl_pipeline_uses_env_default_limit(monkeypatch) -> None:
    called: dict[str, int] = {}

    def fake_fetch_job_id_list(*, session, base_url, group_id, job_id, limit):
        called["limit"] = int(limit)
        return []

    async def fake_upsert_jobs(_records):
        return []

    monkeypatch.setattr(crawler_pipeline, "CRAWLER_FETCH_LIMIT", 350)
    monkeypatch.setattr(crawler_pipeline.requests, "Session", _DummySession)
    monkeypatch.setattr(crawler_pipeline, "fetch_job_id_list", fake_fetch_job_id_list)
    monkeypatch.setattr(crawler_pipeline, "upsert_jobs", fake_upsert_jobs)

    result = await crawler_pipeline.run_crawl_pipeline()
    assert called["limit"] == 350
    assert result.fetched == 0
    assert result.upserted == 0
    assert result.embedded == 0


@pytest.mark.anyio
async def test_run_crawl_pipeline_limit_argument_overrides_env(monkeypatch) -> None:
    called: dict[str, int] = {}

    def fake_fetch_job_id_list(*, session, base_url, group_id, job_id, limit):
        called["limit"] = int(limit)
        return []

    async def fake_upsert_jobs(_records):
        return []

    monkeypatch.setattr(crawler_pipeline, "CRAWLER_FETCH_LIMIT", 350)
    monkeypatch.setattr(crawler_pipeline.requests, "Session", _DummySession)
    monkeypatch.setattr(crawler_pipeline, "fetch_job_id_list", fake_fetch_job_id_list)
    monkeypatch.setattr(crawler_pipeline, "upsert_jobs", fake_upsert_jobs)

    result = await crawler_pipeline.run_crawl_pipeline(limit=120)
    assert called["limit"] == 120
    assert result.fetched == 0
    assert result.upserted == 0
    assert result.embedded == 0


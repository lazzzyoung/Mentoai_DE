from fastapi.testclient import TestClient

from mentoai import ops
from mentoai.api import admin as admin_module
from mentoai.api.main import app
from mentoai.pipeline import runner as runner_module

client = TestClient(app)

USER_PAYLOAD = {
    "username": "새인재",
    "desired_job": "데이터 엔지니어",
    "career_years": 2,
    "skills": ["Python", "SQL"],
}


def test_admin_page_served() -> None:
    response = client.get("/admin")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "관리자" in response.text


def test_stats(monkeypatch) -> None:
    async def fake_status():
        return {
            "bronze": 10, "jobs": 5, "embeddings": 5, "users": 3, "cached_analyses": 1,
            "sizes": {"bronze_size": "16 kB"},
            "embedding_model": "fastembed:intfloat/multilingual-e5-large",
            "embedding_dim": 1024,
            "gemini_model": "gemini-3-flash-preview",
            "schedule": {"enabled": False, "cron": "0 9,16 * * *", "next_run": None},
            "running": [],
            "last_run": {"id": 7, "status": "success"},
        }

    monkeypatch.setattr(ops, "get_status", fake_status)
    response = client.get("/api/v1/admin/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["bronze"] == 10
    assert data["sizes"]["bronze_size"] == "16 kB"
    assert data["schedule"]["cron"] == "0 9,16 * * *"


def test_pipeline_runs_list(monkeypatch) -> None:
    async def fake_runs():
        return [{"id": 3, "status": "success", "error": None}]

    monkeypatch.setattr(ops, "list_runs", fake_runs)
    response = client.get("/api/v1/admin/pipeline-runs")
    assert response.status_code == 200
    assert response.json()[0]["id"] == 3


def test_trigger_pipeline_conflict(monkeypatch) -> None:
    async def fake_fetchrow(*_: object):
        return {"id": 3}

    monkeypatch.setattr(admin_module, "fetchrow", fake_fetchrow)
    response = client.post("/api/v1/admin/pipeline")
    assert response.status_code == 409


def test_trigger_pipeline_started(monkeypatch) -> None:
    async def fake_fetchrow(*_: object):
        return None

    async def fake_run() -> dict:
        return {"scraped": 0, "silver_upserted": 0, "embedded": 0}

    monkeypatch.setattr(admin_module, "fetchrow", fake_fetchrow)
    monkeypatch.setattr(runner_module, "run_pipeline", fake_run)
    response = client.post("/api/v1/admin/pipeline")
    assert response.status_code == 200
    assert response.json() == {"status": "started"}


def test_jobs_list(monkeypatch) -> None:
    captured: dict = {}

    async def fake_jobs(query: str = "", limit: int = 30):
        captured.update(query=query, limit=limit)
        return [{"id": 1, "source": "wanted", "company": "테스트"}]

    monkeypatch.setattr(ops, "list_jobs", fake_jobs)
    response = client.get("/api/v1/admin/jobs?query=테스트&limit=10")
    assert response.status_code == 200
    assert response.json()[0]["company"] == "테스트"
    assert captured == {"query": "테스트", "limit": 10}


def test_delete_job(monkeypatch) -> None:
    async def fake_delete(job_id: int):
        assert job_id == 5
        return {"source": "wanted", "company": "테스트", "position": "DE"}

    monkeypatch.setattr(ops, "delete_job", fake_delete)
    assert client.delete("/api/v1/admin/jobs/5").status_code == 204


def test_delete_job_not_found(monkeypatch) -> None:
    async def fake_delete(*_: object):
        raise KeyError("공고 없음: 9")

    monkeypatch.setattr(ops, "delete_job", fake_delete)
    response = client.delete("/api/v1/admin/jobs/9")
    assert response.status_code == 404
    assert response.json()["detail"] == "공고 없음: 9"


def test_create_user_ok(monkeypatch) -> None:
    async def fake_create(payload):
        return {"id": 9, **payload.model_dump()}

    monkeypatch.setattr(ops, "create_user", fake_create)
    response = client.post("/api/v1/admin/users", json=USER_PAYLOAD)
    assert response.status_code == 201
    assert response.json()["id"] == 9


def test_create_user_conflict(monkeypatch) -> None:
    async def fake_create(*_: object):
        raise ValueError("이미 존재하는 사용자: 새인재")

    monkeypatch.setattr(ops, "create_user", fake_create)
    response = client.post("/api/v1/admin/users", json=USER_PAYLOAD)
    assert response.status_code == 409


def test_create_user_validation() -> None:
    assert client.post("/api/v1/admin/users", json={**USER_PAYLOAD, "username": ""}).status_code == 422
    assert client.post("/api/v1/admin/users", json={**USER_PAYLOAD, "career_years": 99}).status_code == 422


def test_update_user(monkeypatch) -> None:
    async def fake_update(user_id: int, payload):
        assert user_id == 2
        return {"id": 2, **payload.model_dump()}

    monkeypatch.setattr(ops, "update_user", fake_update)
    response = client.put("/api/v1/admin/users/2", json=USER_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["id"] == 2


def test_update_user_not_found(monkeypatch) -> None:
    async def fake_update(*_: object):
        raise KeyError("사용자 없음: 99")

    monkeypatch.setattr(ops, "update_user", fake_update)
    response = client.put("/api/v1/admin/users/99", json=USER_PAYLOAD)
    assert response.status_code == 404


def test_delete_user_not_found(monkeypatch) -> None:
    async def fake_delete(*_: object):
        raise KeyError("사용자 없음: 999")

    monkeypatch.setattr(ops, "delete_user", fake_delete)
    assert client.delete("/api/v1/admin/users/999").status_code == 404


def test_embedding_models(monkeypatch) -> None:
    def fake_models():
        return {"current": "fastembed:intfloat/multilingual-e5-large", "provider": "fastembed"}

    monkeypatch.setattr(ops, "embedding_models", fake_models)
    response = client.get("/api/v1/admin/embedding/models")
    assert response.status_code == 200
    assert response.json()["provider"] == "fastembed"


def test_embedding_rebuild(monkeypatch) -> None:
    async def fake_rebuild() -> int:
        return 120

    monkeypatch.setattr(ops, "rebuild_embeddings", fake_rebuild)
    response = client.post("/api/v1/admin/embedding/rebuild")
    assert response.status_code == 200
    assert response.json() == {"status": "started"}


def test_embedding_rebuild_conflict(monkeypatch) -> None:
    def fake_start(*_: object):
        return False

    monkeypatch.setattr(ops, "start_background", fake_start)
    response = client.post("/api/v1/admin/embedding/rebuild")
    assert response.status_code == 409


def test_embedding_switch_bad_provider() -> None:
    response = client.post("/api/v1/admin/embedding/switch?provider=openai")
    assert response.status_code == 400


def test_embedding_switch_started(monkeypatch) -> None:
    async def fake_switch(provider: str, model: str | None):
        return {"provider": provider, "model": model, "dim": 1024, "re_embedded": 0}

    monkeypatch.setattr(ops, "switch_embedding_model", fake_switch)
    response = client.post("/api/v1/admin/embedding/switch?provider=gemini")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "started"
    assert data["target"] == "gemini:gemini-embedding-001"


def test_cache_list(monkeypatch) -> None:
    async def fake_cache():
        return [{"job_id": 1, "user_id": 1, "username": "지원", "company": "테스트"}]

    monkeypatch.setattr(ops, "list_cache", fake_cache)
    assert client.get("/api/v1/admin/cache").json()[0]["username"] == "지원"


def test_cache_clear(monkeypatch) -> None:
    async def fake_clear() -> int:
        return 2

    monkeypatch.setattr(ops, "clear_cache", fake_clear)
    assert client.delete("/api/v1/admin/cache").json() == {"deleted": 2}

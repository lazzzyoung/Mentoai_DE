from fastapi import HTTPException
from fastapi.testclient import TestClient

from mentoai.ai import analyzer as analyzer_service
from mentoai.ai import recommend as recommend_service
from mentoai.ai import users as users_service
from mentoai.api.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ui_served_at_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "멘토AI" in response.text


def test_static_assets_served() -> None:
    for path in ("/app.css", "/app.js"):
        response = client.get(path)
        assert response.status_code == 200


def test_pwa_manifest_served() -> None:
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#003b5c"
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_pwa_service_worker_served() -> None:
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "CACHE_NAME" in response.text
    assert "/api/" in response.text  # API 경로는 캐시 제외 선언 확인


def test_pwa_icons_served() -> None:
    for path in (
        "/icons/icon-192.png",
        "/icons/icon-512.png",
        "/icons/icon-maskable-512.png",
        "/icons/apple-touch-icon.png",
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")


def test_manifest_linked_from_pages() -> None:
    for path in ("/", "/admin"):
        response = client.get(path)
        assert 'rel="manifest"' in response.text


def test_list_users(monkeypatch) -> None:
    async def fake_list_users():
        return [
            {"id": 1, "username": "지원", "desired_job": "데이터 엔지니어", "career_years": 2},
            {"id": 2, "username": "하늘", "desired_job": "데이터 분석가", "career_years": 1},
        ]

    monkeypatch.setattr(users_service, "list_users", fake_list_users)

    response = client.get("/api/v1/users")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["username"] == "지원"


def test_recommend_jobs_success(monkeypatch) -> None:
    async def fake_recommend(user_id: int):
        assert user_id == 1
        return {
            "user_name": "테스트유저",
            "recommendations": [
                {
                    "job_id": 11,
                    "company": "MentoAI",
                    "title": "Data Engineer",
                    "match_score": 78,
                    "max_score": 100,
                    "reason": "보유 스킬(Python, Airflow)이 포지션 기술스택과 일치",
                }
            ],
        }

    monkeypatch.setattr(recommend_service, "recommend_jobs", fake_recommend)

    response = client.post("/api/v1/jobs/recommend/1")
    assert response.status_code == 200
    data = response.json()
    assert data["user_name"] == "테스트유저"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["job_id"] == 11


def test_recommend_jobs_user_not_found(monkeypatch) -> None:
    async def fake_recommend(_user_id: int):
        raise HTTPException(status_code=404, detail="User not found")

    monkeypatch.setattr(recommend_service, "recommend_jobs", fake_recommend)

    response = client.post("/api/v1/jobs/recommend/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_analyze_job_success(monkeypatch) -> None:
    async def fake_analyze(job_id: int, user_id: int):
        assert job_id == 123
        assert user_id == 1
        return {
            "job_title": "Data Engineer",
            "company_name": "MentoAI",
            "current_score": 72,
            "max_score": 100,
            "analysis_summary": "핵심 기술은 적합하나 운영 경험 보완 필요",
            "required_tech_stack": ["Kafka", "Spark", "Airflow"],
            "action_plan": [
                {
                    "category": "Project",
                    "item_name": "ETL 파이프라인 운영 실습",
                    "description": "배치 파이프라인을 구성해 운영 지표를 수집",
                    "expected_score_up": 8,
                }
            ],
            "interview_tip": "운영 장애 대응 경험을 STAR 형식으로 설명하세요.",
        }

    monkeypatch.setattr(analyzer_service, "analyze_job", fake_analyze)

    response = client.post("/api/v1/jobs/123/analyze/1")
    assert response.status_code == 200
    data = response.json()
    assert data["job_title"] == "Data Engineer"
    assert data["current_score"] == 72


def test_analyze_job_not_found(monkeypatch) -> None:
    async def fake_analyze(_job_id: int, _user_id: int):
        raise HTTPException(status_code=404, detail="해당 공고를 찾을 수 없습니다.")

    monkeypatch.setattr(analyzer_service, "analyze_job", fake_analyze)

    response = client.post("/api/v1/jobs/9999/analyze/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "해당 공고를 찾을 수 없습니다."

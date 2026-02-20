from fastapi import HTTPException
from fastapi.testclient import TestClient

from server.app.api.routes import v3 as v3_routes
from server.app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "MentoAI service is running"}


def test_favicon_served() -> None:
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.headers.get("content-type") in {
        "image/png",
        "image/vnd.microsoft.icon",
        "image/x-icon",
    }


def test_home_page_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Career Job Hub" in response.text

    jobs_page = client.get("/jobs")
    assert jobs_page.status_code == 200
    assert "Career Job Hub" in jobs_page.text


def test_recommend_and_detail_pages_accessible() -> None:
    recommend = client.get("/jobs/recommend")
    assert recommend.status_code == 200
    assert "맞춤 추천 시작" in recommend.text

    detail = client.get("/jobs/detail")
    assert detail.status_code == 200
    assert "공고 상세 분석" in detail.text

    detail_with_id = client.get("/jobs/detail/123")
    assert detail_with_id.status_code == 200
    assert "공고 상세 분석" in detail_with_id.text


def test_v1_v2_endpoints_removed() -> None:
    assert client.get("/api/v1/test/gemini").status_code == 404
    assert client.get("/api/v1/users/1/specs").status_code == 404
    assert client.post("/api/v1/curation/roadmap/1").status_code == 404
    assert client.post("/api/v2/curation/roadmap/1").status_code == 404


def test_recommend_jobs_success(monkeypatch) -> None:
    async def fake_recommend(user_id: int, limit: int | None = None):
        assert user_id == 1
        assert limit is None
        return {
            "user_id": 1,
            "user_name": "테스트유저",
            "user_profile": {
                "desired_job": "데이터 엔지니어",
                "career_years": 2,
                "skills": ["Python", "Spark", "Kafka"],
            },
            "recommendations": [
                {
                    "job_id": 11,
                    "company": "MentoAI",
                    "title": "Data Engineer",
                    "match_score": 78,
                    "max_score": 100,
                    "reason": "기술스택 적합",
                }
            ],
        }

    monkeypatch.setattr(v3_routes.rag_v3_service, "recommend_jobs_list", fake_recommend)

    response = client.post("/api/v3/jobs/recommend/1")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 1
    assert data["user_name"] == "테스트유저"
    assert data["user_profile"]["desired_job"] == "데이터 엔지니어"
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["job_id"] == 11


def test_recommend_jobs_not_found(monkeypatch) -> None:
    async def fake_recommend(_user_id: int, limit: int | None = None):
        assert limit is None
        raise HTTPException(status_code=404, detail="User not found")

    monkeypatch.setattr(v3_routes.rag_v3_service, "recommend_jobs_list", fake_recommend)

    response = client.post("/api/v3/jobs/recommend/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


def test_recommend_jobs_with_dynamic_limit(monkeypatch) -> None:
    async def fake_recommend(user_id: int, limit: int | None = None):
        assert user_id == 1
        assert limit == 15
        return {
            "user_id": 1,
            "user_name": "테스트유저",
            "user_profile": {
                "desired_job": "데이터 엔지니어",
                "career_years": 2,
                "skills": ["Python"],
            },
            "recommendations": [],
        }

    monkeypatch.setattr(v3_routes.rag_v3_service, "recommend_jobs_list", fake_recommend)
    response = client.post("/api/v3/jobs/recommend/1?limit=15")
    assert response.status_code == 200


def test_quick_login_success(monkeypatch) -> None:
    async def fake_quick_login(payload):
        assert payload.user_name == "홍길동"
        assert payload.desired_job == "백엔드"
        assert payload.career_years == 3
        assert payload.skills == ["Python", "FastAPI"]
        return {
            "user_id": 77,
            "user_name": "홍길동",
            "user_profile": {
                "desired_job": "백엔드",
                "career_years": 3,
                "skills": ["Python", "FastAPI"],
            },
        }

    monkeypatch.setattr(v3_routes.rag_v3_service, "quick_login", fake_quick_login)

    response = client.post(
        "/api/v3/auth/quick-login",
        json={
            "user_name": "홍길동",
            "desired_job": "백엔드",
            "career_years": 3,
            "skills": ["Python", "FastAPI"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == 77
    assert data["user_name"] == "홍길동"
    assert data["user_profile"]["desired_job"] == "백엔드"
    assert data["user_profile"]["skills"] == ["Python", "FastAPI"]


def test_analyze_job_detail_success(monkeypatch) -> None:
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
                    "description": "Airflow+Spark 배치 파이프라인을 구성해 운영 지표를 수집",
                    "expected_score_up": 8,
                }
            ],
            "interview_tip": "운영 장애 대응 경험을 STAR 형식으로 설명하세요.",
        }

    monkeypatch.setattr(v3_routes.rag_v3_service, "analyze_job_detail", fake_analyze)

    response = client.post("/api/v3/jobs/123/analyze/1")
    assert response.status_code == 200
    data = response.json()
    assert data["job_title"] == "Data Engineer"
    assert data["company_name"] == "MentoAI"
    assert data["current_score"] == 72


def test_analyze_job_detail_not_found(monkeypatch) -> None:
    async def fake_analyze(_job_id: int, _user_id: int):
        raise HTTPException(status_code=404, detail="해당 공고를 찾을 수 없습니다.")

    monkeypatch.setattr(v3_routes.rag_v3_service, "analyze_job_detail", fake_analyze)

    response = client.post("/api/v3/jobs/9999/analyze/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "해당 공고를 찾을 수 없습니다."

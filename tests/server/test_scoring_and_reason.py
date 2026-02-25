from server.app.repositories.job_repository import JobCandidate
from server.app.services.hybrid_retriever import (
    _blend_final_score,
    _build_reason,
    _compute_profile_score,
    _profile_weights_for_career,
    _role_match_score,
    _skills_match_score,
)
from server.app.services.rag_v3_service import _resolve_recommendation_limit, _to_match_score


def test_match_score_is_probability_like_scale() -> None:
    assert _to_match_score(-0.2) == 0
    assert _to_match_score(0.0) == 0
    assert _to_match_score(0.25) == 35
    assert _to_match_score(0.5) == 70
    assert _to_match_score(0.75) == 85
    assert _to_match_score(1.0) == 100
    assert _to_match_score(1.3) == 100


def test_reason_message_is_restored_to_previous_tone() -> None:
    candidate = JobCandidate(
        job_id=1,
        company="테스트",
        title="데이터 엔지니어",
        content="",
        skills_text="Python, SQL",
        bm25_score=0.0,
    )

    candidate_without_skills = JobCandidate(
        job_id=2,
        company="테스트",
        title="데이터 엔지니어",
        content="",
        skills_text="",
        bm25_score=0.0,
    )

    assert _build_reason(candidate, 0.9) == "경험과 기술 맥락이 공고 요구사항과 잘 맞습니다."
    assert "일부 일치" in _build_reason(candidate, 0.3)
    assert (
        _build_reason(candidate_without_skills, 0.3) == "희망 직무와 공고 핵심 내용이 유사합니다."
    )


def test_resolve_recommendation_limit_keeps_enough_pool_for_paging(monkeypatch) -> None:
    monkeypatch.setattr("server.app.services.rag_v3_service.RECOMMENDATION_LIMIT", 5)
    monkeypatch.setattr("server.app.services.rag_v3_service.CANDIDATE_LIMIT", 50)
    assert _resolve_recommendation_limit() == 20


def test_resolve_recommendation_limit_respects_candidate_ceiling(monkeypatch) -> None:
    monkeypatch.setattr("server.app.services.rag_v3_service.RECOMMENDATION_LIMIT", 30)
    monkeypatch.setattr("server.app.services.rag_v3_service.CANDIDATE_LIMIT", 12)
    assert _resolve_recommendation_limit() == 12


def test_resolve_recommendation_limit_uses_requested_limit(monkeypatch) -> None:
    monkeypatch.setattr("server.app.services.rag_v3_service.RECOMMENDATION_LIMIT", 20)
    monkeypatch.setattr("server.app.services.rag_v3_service.CANDIDATE_LIMIT", 50)
    assert _resolve_recommendation_limit(35) == 35


def test_resolve_recommendation_limit_clamps_requested_limit(monkeypatch) -> None:
    monkeypatch.setattr("server.app.services.rag_v3_service.CANDIDATE_LIMIT", 12)
    assert _resolve_recommendation_limit(99) == 12


def test_profile_weights_follow_career_bucket() -> None:
    assert _profile_weights_for_career(1) == (0.35, 0.50, 0.15)
    assert _profile_weights_for_career(4) == (0.35, 0.40, 0.25)
    assert _profile_weights_for_career(9) == (0.30, 0.30, 0.40)


def test_profile_score_changes_by_user_career() -> None:
    candidate = JobCandidate(
        job_id=3,
        company="테스트",
        title="데이터 엔지니어",
        content="경력 7년 이상, 데이터 파이프라인 운영 경험",
        skills_text="Python, SQL, Airflow",
        bm25_score=0.0,
    )

    junior = _compute_profile_score(
        candidate,
        desired_job="데이터 엔지니어",
        career_years=1,
        skills=["Python", "SQL"],
    )
    senior = _compute_profile_score(
        candidate,
        desired_job="데이터 엔지니어",
        career_years=8,
        skills=["Python", "SQL"],
    )

    assert senior[2] > junior[2]  # career_score
    assert senior[3] > junior[3]  # profile_score


def test_blend_final_score_uses_retrieval_weight(monkeypatch) -> None:
    monkeypatch.setattr("server.app.services.hybrid_retriever.RANK_RETRIEVAL_WEIGHT", 0.7)
    assert _blend_final_score(0.2, 0.8) == 0.38


def test_reason_highlights_career_gap_when_needed() -> None:
    candidate = JobCandidate(
        job_id=4,
        company="테스트",
        title="데이터 엔지니어",
        content="경력 7년 이상",
        skills_text="Python, SQL",
        bm25_score=0.0,
    )
    reason = _build_reason(
        candidate,
        semantic_score=0.8,
        role_score=0.9,
        skills_score=0.9,
        career_score=0.2,
    )
    assert "경력" in reason


def test_role_match_supports_korean_and_english_backend_aliases() -> None:
    backend_candidate = JobCandidate(
        job_id=5,
        company="테스트",
        title="백엔드 엔지니어",
        content="결제 서버 운영",
        skills_text="Java, Spring",
        bm25_score=0.0,
    )
    frontend_candidate = JobCandidate(
        job_id=6,
        company="테스트",
        title="프론트엔드 개발자",
        content="React 기반 웹 프론트 개발",
        skills_text="TypeScript, React",
        bm25_score=0.0,
    )

    assert _role_match_score("backend", backend_candidate) >= 0.9
    assert _role_match_score("backend", frontend_candidate) <= 0.1


def test_skills_match_splits_compound_skill_text() -> None:
    candidate = JobCandidate(
        job_id=7,
        company="테스트",
        title="백엔드 엔지니어",
        content="JPA와 Hibernate 기반으로 도메인 모델링을 진행합니다.",
        skills_text="",
        bm25_score=0.0,
    )

    assert _skills_match_score(["JPA/Hibernate"], candidate) == 1.0


def test_role_match_groups_data_engineer_family_flexibly() -> None:
    data_platform_candidate = JobCandidate(
        job_id=8,
        company="테스트",
        title="Data Platform Engineer",
        content="대용량 데이터 파이프라인과 웨어하우스를 구축합니다.",
        skills_text="Python, Spark",
        bm25_score=0.0,
    )
    backend_candidate = JobCandidate(
        job_id=9,
        company="테스트",
        title="백엔드 엔지니어",
        content="API/서버 설계",
        skills_text="Java, Spring",
        bm25_score=0.0,
    )
    marketer_candidate = JobCandidate(
        job_id=10,
        company="테스트",
        title="브랜드 마케터",
        content="브랜드 캠페인 기획",
        skills_text="",
        bm25_score=0.0,
    )

    assert _role_match_score("데이터 엔지니어", data_platform_candidate) >= 0.9
    assert _role_match_score("데이터 엔지니어", backend_candidate) >= 0.5
    assert _role_match_score("데이터 엔지니어", marketer_candidate) <= 0.1


def test_role_match_accepts_front_korean_variants() -> None:
    frontend_candidate = JobCandidate(
        job_id=11,
        company="테스트",
        title="프런트엔드 개발자",
        content="React 기반 UI 개발",
        skills_text="React, TypeScript",
        bm25_score=0.0,
    )
    backend_candidate = JobCandidate(
        job_id=12,
        company="테스트",
        title="백엔드 개발자",
        content="Spring 기반 API 개발",
        skills_text="Java, Spring",
        bm25_score=0.0,
    )

    assert _role_match_score("front", frontend_candidate) >= 0.9
    assert _role_match_score("프론트", frontend_candidate) >= 0.9
    assert _role_match_score("프런트", frontend_candidate) >= 0.9
    assert _role_match_score("프론트", backend_candidate) <= 0.1

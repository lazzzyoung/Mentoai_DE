from server.app.repositories.job_repository import JobCandidate
from server.app.services.hybrid_retriever import _build_reason
from server.app.services.rag_v3_service import _to_match_score


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
    assert _build_reason(candidate_without_skills, 0.3) == "희망 직무와 공고 핵심 내용이 유사합니다."

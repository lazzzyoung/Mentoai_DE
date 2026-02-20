from server.app.repositories.job_repository import JobCandidate
from server.app.services.hybrid_retriever import _build_reason
from server.app.services.rag_v3_service import _to_match_score


def test_match_score_is_probability_like_scale() -> None:
    assert _to_match_score(-0.2) == 0
    assert _to_match_score(0.0) == 0
    assert _to_match_score(0.5) == 50
    assert _to_match_score(1.0) == 100
    assert _to_match_score(1.3) == 100


def test_reason_message_is_not_overly_positive() -> None:
    candidate = JobCandidate(
        job_id=1,
        company="테스트",
        title="데이터 엔지니어",
        content="",
        skills_text="Python, SQL",
        bm25_score=0.0,
    )

    assert _build_reason(candidate, 0.9) == "요구 기술·경험과의 일치도가 높은 편입니다."
    assert "보통 수준" in _build_reason(candidate, 0.7)
    assert "일부 일치" in _build_reason(candidate, 0.3)

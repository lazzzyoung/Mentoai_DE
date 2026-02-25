from server.app.repositories.job_repository import _build_match_query


def test_build_match_query_removes_profile_labels_and_year_token() -> None:
    query = _build_match_query("희망직무: backend, 보유기술: JPA/Hibernate, 경력: 3년")

    assert "희망직무" not in query
    assert "보유기술" not in query
    assert "경력" not in query
    assert "3년" not in query
    assert "backend" in query


from server.app.repositories.job_repository import _build_match_query


def test_build_match_query_removes_profile_labels_and_year_token() -> None:
    query = _build_match_query("희망직무: backend, 보유기술: JPA/Hibernate, 경력: 3년")

    assert "희망직무" not in query
    assert "보유기술" not in query
    assert "경력" not in query
    assert "3년" not in query
    assert "backend" in query


def test_build_match_query_expands_data_engineer_phrase() -> None:
    query = _build_match_query("희망직무: 데이터 엔지니어, 보유기술: Python, 경력: 5년")

    assert "데이터 엔지니어" in query
    assert "data engineer" in query
    assert "etl" in query


def test_build_match_query_expands_front_variants() -> None:
    query = _build_match_query("희망직무: 프런트, 보유기술: React, 경력: 2년")

    assert "프런트" in query
    assert "frontend" in query
    assert "front" in query

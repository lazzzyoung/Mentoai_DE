import pytest

from server.app.db.session import reset_db_for_tests
from server.app.repositories import job_repository
from server.app.repositories.job_repository import JobRecord
from server.app.services.crawler_pipeline import _to_record


def test_to_record_uses_detail_position_when_top_level_is_missing() -> None:
    record = _to_record(
        101,
        {
            "company": {"name": "테스트회사"},
            "detail": {"position": "데이터 엔지니어"},
            "skill_tags": [{"name": "Python"}],
        },
    )

    assert record.position == "데이터 엔지니어"
    assert "[포지션] 데이터 엔지니어" in record.full_text


def test_to_record_extracts_skill_tags_from_text_key() -> None:
    record = _to_record(
        102,
        {
            "company": {"name": "테스트회사"},
            "position": "백엔드 엔지니어",
            "skill_tags": [{"text": "Java"}, {"text": "Spring Boot"}],
            "preferred_languages": [{"text": "Kotlin"}],
            "detail": {},
        },
    )

    assert record.skills_text == "Java, Spring Boot, Kotlin"


@pytest.mark.anyio
async def test_search_and_detail_fallback_to_position_from_full_text(tmp_path) -> None:
    db_file = tmp_path / "job_title.db"
    reset_db_for_tests(str(db_file))

    full_text = "\n".join(
        [
            "[회사] 테스트회사",
            "[포지션] 데이터 엔지니어",
            "[소개] 테스트 소개",
        ]
    )
    records = [
        JobRecord(
            source="wanted",
            source_id="501",
            company="테스트회사",
            position="미상",
            full_text=full_text,
            skills_text="Python, SQL",
            collected_at="2026-02-20T00:00:00Z",
        )
    ]

    upserted_ids = await job_repository.upsert_jobs(records)
    assert len(upserted_ids) == 1
    job_id = upserted_ids[0]

    candidates = await job_repository.search_jobs_fts("데이터", limit=5)
    assert candidates
    assert candidates[0].job_id == job_id
    assert candidates[0].title == "데이터 엔지니어"

    detail = await job_repository.fetch_job_detail(job_id)
    assert detail["title"] == "데이터 엔지니어"

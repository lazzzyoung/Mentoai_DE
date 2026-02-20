import pytest
from fastapi import HTTPException

from server.app.db.session import reset_db_for_tests
from server.app.repositories import user_repository as repo


@pytest.mark.anyio
async def test_create_and_fetch_user_info(tmp_path):
    db_file = tmp_path / "user_repo.db"
    reset_db_for_tests(str(db_file))

    user_id = await repo.create_quick_user(
        user_name="홍길동",
        desired_job="데이터 엔지니어",
        career_years=2,
        skills=["Python", "Spark"],
    )

    user = await repo.fetch_user_info(user_id)

    assert user_id > 0
    assert user["username"] == "홍길동"
    assert user["desired_job"] == "데이터 엔지니어"
    assert user["career_years"] == 2
    assert user["skills"] == ["Python", "Spark"]


@pytest.mark.anyio
async def test_quick_user_upsert_updates_spec(tmp_path):
    db_file = tmp_path / "user_repo_upsert.db"
    reset_db_for_tests(str(db_file))

    first_id = await repo.create_quick_user(
        user_name="테스트",
        desired_job="백엔드",
        career_years=1,
        skills=["Python"],
    )
    second_id = await repo.create_quick_user(
        user_name="테스트",
        desired_job="플랫폼",
        career_years=3,
        skills=["Python", "SQL"],
    )

    user = await repo.fetch_user_info(first_id)

    assert first_id == second_id
    assert user["desired_job"] == "플랫폼"
    assert user["career_years"] == 3
    assert user["skills"] == ["Python", "SQL"]


@pytest.mark.anyio
async def test_create_quick_user_invalid_career_years(tmp_path):
    db_file = tmp_path / "user_repo_invalid.db"
    reset_db_for_tests(str(db_file))

    with pytest.raises(HTTPException) as exc_info:
        await repo.create_quick_user(
            user_name="사용자",
            desired_job="데이터",
            career_years=-1,
            skills=["Python"],
        )

    assert exc_info.value.status_code == 400
    assert "경력(년)은 0 이상의 숫자" in str(exc_info.value.detail)

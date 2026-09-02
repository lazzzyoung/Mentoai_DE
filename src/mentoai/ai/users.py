from typing import Any

from fastapi import HTTPException

from mentoai.db.pool import fetch, fetchrow


async def list_users() -> list[dict[str, Any]]:
    rows = await fetch(
        """
        SELECT u.id, u.username, s.desired_job, s.career_years
        FROM users u
        JOIN user_specs s ON s.user_id = u.id
        ORDER BY u.id
        """
    )
    return [dict(r) for r in rows]


async def fetch_user_info(user_id: int) -> dict[str, Any]:
    row = await fetchrow(
        """
        SELECT u.username, s.desired_job, s.career_years, s.skills
        FROM user_specs s
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id = $1
        """,
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


def build_profile_text(user: dict[str, Any]) -> str:
    return (
        f"희망직무: {user['desired_job']}, "
        f"보유기술: {', '.join(user['skills'] or [])}, "
        f"경력: {user['career_years']}년"
    )

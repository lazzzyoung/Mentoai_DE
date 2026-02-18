from typing import Any

from fastapi import HTTPException

from server.app.core.config import DB_URL


def fetch_user_info(user_id: int) -> dict[str, Any]:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT u.username, s.desired_job, s.career_years, s.skills
            FROM user_specs s
            JOIN users u ON s.user_id = u.id
            WHERE s.user_id = %s
            """,
            (user_id,),
        )
        user_info = cur.fetchone()
        if not user_info:
            raise HTTPException(404, "User not found")
        return dict(user_info)
    finally:
        if conn:
            conn.close()

from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


class UserRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _fetch_one(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with psycopg2.connect(self.database_url) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None

    def fetch_user_profile(self, user_id: int) -> dict[str, Any] | None:
        query = (
            "SELECT u.username, s.desired_job, s.career_years, s.skills "
            "FROM user_specs s "
            "JOIN users u ON s.user_id = u.id "
            "WHERE s.user_id = %s"
        )
        return self._fetch_one(query, (user_id,))

    def fetch_user_specs(self, user_id: int) -> dict[str, Any] | None:
        query = "SELECT * FROM user_specs WHERE user_id = %s"
        return self._fetch_one(query, (user_id,))

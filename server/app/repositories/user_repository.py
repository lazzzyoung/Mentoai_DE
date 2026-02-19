from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from server.app.core.config import DB_URL

_pool: Any | None = None
_pool_lock: Any | None = None
_schema_initialized = False
_schema_lock: Any | None = None


def _normalize_user_name(user_name: str) -> str:
    normalized = (user_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="이름은 필수 입력 항목입니다.")
    return normalized


def _normalize_skills(skills: list[str]) -> list[str]:
    normalized: list[str] = []
    for skill in skills:
        text = (skill or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _slugify_username(value: str) -> str:
    raw = (value or "").strip().lower().replace(" ", "_")
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)
    return safe.strip("_") or "user"


def _get_lock() -> Any:
    global _pool_lock
    if _pool_lock is None:
        import asyncio

        _pool_lock = asyncio.Lock()
    return _pool_lock


def _get_schema_lock() -> Any:
    global _schema_lock
    if _schema_lock is None:
        import asyncio

        _schema_lock = asyncio.Lock()
    return _schema_lock


async def _get_pool() -> Any:
    global _pool

    if _pool is not None:
        return _pool

    lock = _get_lock()
    async with lock:
        if _pool is None:
            import asyncpg

            _pool = await asyncpg.create_pool(dsn=DB_URL, min_size=1, max_size=10)

    return _pool


async def _ensure_user_tables() -> None:
    global _schema_initialized

    if _schema_initialized:
        return

    lock = _get_schema_lock()
    async with lock:
        if _schema_initialized:
            return

        pool = await _get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_specs (
                    spec_id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id) ON DELETE CASCADE,
                    desired_job VARCHAR(100),
                    career_years INT DEFAULT 0,
                    education VARCHAR(100),
                    skills TEXT[],
                    certificates TEXT[],
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_specs_user_id
                ON user_specs (user_id)
                """
            )
            await conn.execute(
                """
                DELETE FROM user_specs older
                USING user_specs newer
                WHERE older.user_id = newer.user_id
                  AND older.spec_id < newer.spec_id
                """
            )
            await conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_user_specs_user_id
                ON user_specs (user_id)
                """
            )

        _schema_initialized = True


async def _resolve_column_exists(conn: Any, table: str, column: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = $1
                  AND column_name = $2
            )
            """,
            table,
            column,
        )
    )


async def fetch_user_info(user_id: int) -> dict[str, Any]:
    await _ensure_user_tables()
    pool = await _get_pool()
    async with pool.acquire() as conn:
        user_column = (
            "username" if await _resolve_column_exists(conn, "users", "username") else "name"
        )
        desired_job_col = (
            "s.desired_job"
            if await _resolve_column_exists(conn, "user_specs", "desired_job")
            else "NULL"
        )
        career_years_col = (
            "s.career_years"
            if await _resolve_column_exists(conn, "user_specs", "career_years")
            else "NULL"
        )
        skills_col = (
            "s.skills"
            if await _resolve_column_exists(conn, "user_specs", "skills")
            else "ARRAY[]::text[]"
        )
        has_specs = await _resolve_column_exists(conn, "user_specs", "user_id")

        if has_specs:
            query = f"""
                SELECT u.{user_column} AS username, {desired_job_col} AS desired_job, {career_years_col} AS career_years, {skills_col} AS skills
                FROM users u
                LEFT JOIN user_specs s ON s.user_id = u.id
                WHERE u.id = $1
                LIMIT 1
            """
            user_info = await conn.fetchrow(query, user_id)
        else:
            query = f"""
                SELECT u.{user_column} AS username, NULL AS desired_job, NULL AS career_years, NULL AS skills
                FROM users u
                WHERE u.id = $1
                LIMIT 1
            """
            user_info = await conn.fetchrow(query, user_id)

    if not user_info:
        raise HTTPException(404, "계정을 찾을 수 없습니다.")
    return dict(user_info)


async def create_quick_user(
    user_name: str,
    desired_job: str,
    career_years: int,
    skills: list[str],
) -> int:
    await _ensure_user_tables()
    name = _normalize_user_name(user_name)
    normalized_job = (desired_job or "미입력").strip() or "미입력"
    normalized_skills = _normalize_skills(skills)

    try:
        career_years_int = int(career_years)
        if career_years_int < 0:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="경력(년)은 0 이상의 숫자로 입력해 주세요.",
        ) from error

    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_id_col = (
                "username" if await _resolve_column_exists(conn, "users", "username") else "name"
            )
            if not await _resolve_column_exists(conn, "users", user_id_col):
                raise HTTPException(
                    status_code=500,
                    detail="계정을 생성하는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
                )

            user_columns: list[str] = [user_id_col]
            query_values: list[Any] = [name]
            has_email_column = await _resolve_column_exists(conn, "users", "email")

            if has_email_column:
                email = f"{_slugify_username(name)}_{uuid4().hex[:8]}@local.mentoai"
                user_columns.append("email")
                query_values.append(email)

            user_placeholders = [f"${index + 1}" for index in range(len(query_values))]
            if user_id_col == "username":
                query = f"""
                    INSERT INTO users ({", ".join(user_columns)})
                    VALUES ({", ".join(user_placeholders)})
                    ON CONFLICT (username)
                    DO UPDATE SET username = EXCLUDED.username
                    RETURNING id
                """
            else:
                query = f"""
                    INSERT INTO users ({", ".join(user_columns)})
                    VALUES ({", ".join(user_placeholders)})
                    RETURNING id
                """

            user_id = await conn.fetchval(query, *query_values)

            spec_columns: list[str] = []
            spec_values: list[Any] = []

            if await _resolve_column_exists(conn, "user_specs", "user_id"):
                spec_columns.append("user_id")
                spec_values.append(user_id)

            if await _resolve_column_exists(conn, "user_specs", "desired_job"):
                spec_columns.append("desired_job")
                spec_values.append(normalized_job)

            if await _resolve_column_exists(conn, "user_specs", "career_years"):
                spec_columns.append("career_years")
                spec_values.append(career_years_int)

            if await _resolve_column_exists(conn, "user_specs", "skills"):
                spec_columns.append("skills")
                spec_values.append(normalized_skills)

            if spec_columns:
                spec_placeholders = [f"${index + 1}" for index in range(len(spec_values))]
                has_updated_at_col = await _resolve_column_exists(conn, "user_specs", "updated_at")

                if "user_id" in spec_columns:
                    updatable_columns = [column for column in spec_columns if column != "user_id"]
                    if updatable_columns:
                        update_clauses = [
                            f"{column} = EXCLUDED.{column}" for column in updatable_columns
                        ]
                        if has_updated_at_col:
                            update_clauses.append("updated_at = CURRENT_TIMESTAMP")
                        spec_insert = f"""
                            INSERT INTO user_specs ({", ".join(spec_columns)})
                            VALUES ({", ".join(spec_placeholders)})
                            ON CONFLICT (user_id)
                            DO UPDATE SET {", ".join(update_clauses)}
                        """
                    else:
                        spec_insert = f"""
                            INSERT INTO user_specs ({", ".join(spec_columns)})
                            VALUES ({", ".join(spec_placeholders)})
                            ON CONFLICT (user_id) DO NOTHING
                        """
                else:
                    spec_insert = f"""
                        INSERT INTO user_specs ({", ".join(spec_columns)})
                        VALUES ({", ".join(spec_placeholders)})
                    """
                await conn.execute(spec_insert, *spec_values)

            return user_id


async def close_pool() -> None:
    global _pool, _schema_initialized

    if _pool is not None:
        await _pool.close()
        _pool = None
    _schema_initialized = False

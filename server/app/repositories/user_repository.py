from typing import Any

from fastapi import HTTPException

from server.app.core.config import DB_URL

_pool: Any | None = None
_pool_lock: Any | None = None


def _get_lock() -> Any:
    global _pool_lock
    if _pool_lock is None:
        import asyncio

        _pool_lock = asyncio.Lock()
    return _pool_lock


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


async def fetch_user_info(user_id: int) -> dict[str, Any]:
    pool = await _get_pool()
    query = """
        SELECT u.username, s.desired_job, s.career_years, s.skills
        FROM user_specs s
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id = $1
    """
    async with pool.acquire() as conn:
        user_info = await conn.fetchrow(query, user_id)

    if not user_info:
        raise HTTPException(404, "User not found")
    return dict(user_info)


async def close_pool() -> None:
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None

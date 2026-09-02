import asyncio
import json
from collections.abc import Sequence
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from mentoai.config import get_settings

_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


async def _init_connection(conn: asyncpg.Connection) -> None:
    try:
        await register_vector(conn)
    except ValueError:
        # 최초 마이그레이션 전에는 vector 타입이 없다 - 확장 설치 후 재시도
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                dsn=get_settings().database_url,
                min_size=1,
                max_size=10,
                init=_init_connection,
            )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def executemany(query: str, args: Sequence[Sequence[Any]]) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(query, args)

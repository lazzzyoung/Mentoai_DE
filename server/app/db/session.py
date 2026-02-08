from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.core.config import get_settings


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql+"):
        _, rest = database_url.split("://", 1)
        return f"postgresql+asyncpg://{rest}"
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


@lru_cache
def get_async_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(database_url),
        pool_pre_ping=True,
    )


@lru_cache
def get_async_sessionmaker(database_url: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(database_url),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_async_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    session_maker = get_async_sessionmaker(settings.database_url)

    async with session_maker() as session:
        yield session

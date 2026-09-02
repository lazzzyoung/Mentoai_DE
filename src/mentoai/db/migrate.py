import logging
from pathlib import Path

from mentoai.db.pool import get_pool

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def apply_migrations() -> list[str]:
    """migrations/*.sql 을 파일명 순서대로 한 번씩만 적용한다."""
    pool = await get_pool()
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        done = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)", path.name
                )
            applied.append(path.name)
            logger.info("migration applied: %s", path.name)
    return applied


EMBEDDINGS_DDL = """
CREATE TABLE silver.job_embeddings (
    job_id bigint PRIMARY KEY REFERENCES silver.jobs(id) ON DELETE CASCADE,
    embedding vector({dim}) NOT NULL,
    model text NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_embeddings_hnsw
    ON silver.job_embeddings USING hnsw (embedding vector_cosine_ops);
"""


async def recreate_job_embeddings(dim: int) -> None:
    """임베딩 테이블을 {dim}차원으로 새로 만든다. 임베딩은 파생 데이터라 재생성이 안전하다."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS silver.job_embeddings")
        await conn.execute(EMBEDDINGS_DDL.format(dim=dim))
    logger.info("job_embeddings 테이블 재생성: vector(%d)", dim)

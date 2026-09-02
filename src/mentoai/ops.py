"""CLI와 어드민 API가 공유하는 운영 작업 계층.

한 곳에 구현해 두 인터페이스가 항상 같은 로직을 돌린다.
"""

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

from mentoai.ai.embeddings import model_key
from mentoai.config import get_settings
from mentoai.db.pool import execute, fetch, fetchrow

logger = logging.getLogger(__name__)


# ---------- 백그라운드 작업 가드 ----------

_running: set[str] = set()


def start_background(name: str, factory) -> bool:
    """factory: 인자 없는 코루틴 팩토리. 동일 이름 작업이 이미 돌면 False.

    팩토리를 받는 이유: 가드에 걸린 호출에서 코루틴이 생성만 되고
    await되지 않는 'never awaited' 경로를 원천 차단한다.
    """
    if name in _running:
        return False
    task = asyncio.create_task(factory())
    _running.add(name)
    task.add_done_callback(lambda _: _running.discard(name))
    return True


def running_ops() -> list[str]:
    return sorted(_running)


# ---------- 현황 ----------

async def get_status() -> dict[str, Any]:
    settings = get_settings()
    counts = await fetchrow(
        """
        SELECT
          (SELECT count(*) FROM bronze.raw_postings) AS bronze,
          (SELECT count(*) FROM silver.jobs) AS jobs,
          (SELECT count(*) FROM silver.job_embeddings) AS embeddings,
          (SELECT count(*) FROM users) AS users,
          (SELECT count(*) FROM analysis_cache) AS cached_analyses
        """
    )
    assert counts is not None
    sizes = await fetchrow(
        """
        SELECT
          pg_size_pretty(pg_total_relation_size('bronze.raw_postings'::regclass)) AS bronze_size,
          pg_size_pretty(pg_total_relation_size('silver.jobs'::regclass)) AS jobs_size,
          pg_size_pretty(pg_total_relation_size('silver.job_embeddings'::regclass)) AS embeddings_size
        """
    )
    last_run = await fetchrow(
        """
        SELECT id, status, started_at, finished_at, scraped, silver_upserted, embedded
        FROM pipeline_runs ORDER BY id DESC LIMIT 1
        """
    )

    from mentoai.api.scheduler import schedule_info

    return {
        **dict(counts),
        "sizes": dict(sizes) if sizes else {},
        "embedding_model": model_key(),
        "embedding_dim": settings.embedding_dim,
        "gemini_model": settings.gemini_model,
        "schedule": schedule_info(),
        "running": running_ops(),
        "last_run": dict(last_run) if last_run else None,
    }


async def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    rows = await fetch(
        """
        SELECT id, status, started_at, finished_at, scraped, silver_upserted, embedded, error
        FROM pipeline_runs ORDER BY id DESC LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


# ---------- 공고 ----------

async def list_jobs(query: str = "", limit: int = 30) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    if query:
        rows = await fetch(
            """
            SELECT id, source, source_id, company, position, skill_tags, updated_at
            FROM silver.jobs
            WHERE company ILIKE $1 OR position ILIKE $1
            ORDER BY updated_at DESC LIMIT $2
            """,
            f"%{query}%",
            limit,
        )
    else:
        rows = await fetch(
            """
            SELECT id, source, source_id, company, position, skill_tags, updated_at
            FROM silver.jobs ORDER BY updated_at DESC LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def delete_job(job_id: int) -> dict[str, Any]:
    """silver 공고와 대응하는 bronze 원본까지 지운다 (임베딩/캐시는 cascade)."""
    job = await fetchrow(
        "SELECT source, source_id, company, position FROM silver.jobs WHERE id = $1", job_id
    )
    if not job:
        raise KeyError(f"공고 없음: {job_id}")
    await execute("DELETE FROM silver.jobs WHERE id = $1", job_id)
    await execute(
        "DELETE FROM bronze.raw_postings WHERE source = $1 AND source_id = $2",
        job["source"],
        job["source_id"],
    )
    logger.info("공고 삭제: #%s %s %s", job_id, job["company"], job["position"])
    return dict(job)


# ---------- 인재 ----------

class UserPayload(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    desired_job: str = Field(min_length=1, max_length=60)
    career_years: int = Field(ge=0, le=40)
    skills: list[str] = Field(default_factory=list, max_length=20)


async def create_user(payload: UserPayload) -> dict[str, Any]:
    row = await fetchrow(
        "INSERT INTO users (username) VALUES ($1) ON CONFLICT (username) DO NOTHING RETURNING id",
        payload.username,
    )
    if row is None:
        raise ValueError(f"이미 존재하는 사용자: {payload.username}")
    await _upsert_spec(row["id"], payload)
    return {"id": row["id"], **payload.model_dump()}


async def update_user(user_id: int, payload: UserPayload) -> dict[str, Any]:
    row = await fetchrow("SELECT id, username FROM users WHERE id = $1", user_id)
    if not row:
        raise KeyError(f"사용자 없음: {user_id}")
    await _upsert_spec(user_id, payload)
    return {"id": user_id, **payload.model_dump()}


async def _upsert_spec(user_id: int, payload: UserPayload) -> None:
    await execute(
        """
        INSERT INTO user_specs (user_id, desired_job, career_years, skills)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET
            desired_job = EXCLUDED.desired_job,
            career_years = EXCLUDED.career_years,
            skills = EXCLUDED.skills
        """,
        user_id,
        payload.desired_job,
        payload.career_years,
        payload.skills,
    )


async def find_user_by_name(username: str) -> dict[str, Any] | None:
    row = await fetchrow("SELECT id, username FROM users WHERE username = $1", username)
    return dict(row) if row else None


async def delete_user(user_id: int) -> None:
    result = await execute("DELETE FROM users WHERE id = $1", user_id)
    if result == "DELETE 0":
        raise KeyError(f"사용자 없음: {user_id}")


# ---------- 임베딩 ----------

async def rebuild_embeddings() -> int:
    """전량 재계산: 임베딩은 파생 데이터라 전체 삭제 후 재적재한다."""
    await execute("DELETE FROM silver.job_embeddings")
    from mentoai.pipeline import gold

    return await gold.run()


def embedding_models() -> dict[str, Any]:
    from fastembed import TextEmbedding

    return {
        "current": model_key(),
        "provider": get_settings().embedding_provider,
        "dim": get_settings().embedding_dim,
        "fastembed": sorted(
            (
                {"model": m["model"], "dim": m["dim"], "size_gb": m["size_in_GB"]}
                for m in TextEmbedding.list_supported_models()
            ),
            key=lambda m: m["model"],
        ),
        "gemini_default": "gemini-embedding-001",
    }


async def switch_embedding_model(provider: str, model: str | None) -> dict[str, Any]:
    from mentoai.embed_switch import switch_embedding

    return await switch_embedding(provider=provider, model=model)


# ---------- 캐시 ----------

async def list_cache() -> list[dict[str, Any]]:
    rows = await fetch(
        """
        SELECT c.job_id, c.user_id, c.model, c.created_at,
               u.username, j.company, j.position
        FROM analysis_cache c
        JOIN users u ON u.id = c.user_id
        JOIN silver.jobs j ON j.id = c.job_id
        ORDER BY c.created_at DESC LIMIT 20
        """
    )
    return [dict(r) for r in rows]


async def clear_cache() -> int:
    rows = await fetch("DELETE FROM analysis_cache RETURNING job_id")
    return len(rows)


async def delete_cache(job_id: int, user_id: int) -> None:
    result = await execute(
        "DELETE FROM analysis_cache WHERE job_id = $1 AND user_id = $2", job_id, user_id
    )
    if result == "DELETE 0":
        raise KeyError(f"캐시 없음: job={job_id} user={user_id}")

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select

from server.app.db import session_scope
from server.app.models import Job, JobEmbedding

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣_+#.-]+")


@dataclass(slots=True)
class JobRecord:
    source: str
    source_id: str
    company: str
    position: str
    full_text: str
    skills_text: str
    collected_at: str


@dataclass(slots=True)
class JobCandidate:
    job_id: int
    company: str
    title: str
    content: str
    skills_text: str
    bm25_score: float


def _build_match_query(user_query: str) -> str:
    tokens = [token.strip() for token in TOKEN_PATTERN.findall(user_query or "") if token.strip()]
    unique_tokens: list[str] = []
    seen: set[str] = set()

    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        unique_tokens.append(token)
        seen.add(key)

    return " OR ".join(unique_tokens[:10])


def _sync_jobs_fts(session: Any, job: Job) -> None:
    session.exec(
        cast(Any, text("DELETE FROM jobs_fts WHERE job_id = :job_id")), params={"job_id": job.id}
    )
    session.exec(
        cast(
            Any,
            text(
                """
            INSERT INTO jobs_fts (job_id, company, position, full_text, skills_text)
            VALUES (:job_id, :company, :position, :full_text, :skills_text)
            """
            ),
        ),
        params={
            "job_id": job.id,
            "company": job.company,
            "position": job.position,
            "full_text": job.full_text,
            "skills_text": job.skills_text,
        },
    )


async def upsert_jobs(records: list[JobRecord]) -> list[int]:
    if not records:
        return []

    upserted_ids: list[int] = []

    with session_scope() as session:
        for record in records:
            stmt = select(Job).where(Job.source == record.source, Job.source_id == record.source_id)
            job = session.exec(stmt).first()
            if job is None:
                job = Job(
                    source=record.source,
                    source_id=record.source_id,
                    company=record.company,
                    position=record.position,
                    full_text=record.full_text,
                    skills_text=record.skills_text,
                    collected_at=record.collected_at,
                )
                session.add(job)
                session.commit()
                session.refresh(job)
            else:
                job.company = record.company
                job.position = record.position
                job.full_text = record.full_text
                job.skills_text = record.skills_text
                job.collected_at = record.collected_at
                job.updated_at = datetime.now(UTC)
                session.add(job)
                session.commit()

            if job.id is None:
                continue

            _sync_jobs_fts(session, job)
            session.commit()
            upserted_ids.append(int(job.id))

    return upserted_ids


async def upsert_embedding(job_id: int, vector: list[float]) -> None:
    with session_scope() as session:
        embedding = session.get(JobEmbedding, job_id)
        payload = json.dumps(vector, ensure_ascii=False)

        if embedding is None:
            session.add(JobEmbedding(job_id=job_id, vector_json=payload))
        else:
            embedding.vector_json = payload
            embedding.updated_at = datetime.now(UTC)
            session.add(embedding)
        session.commit()


async def fetch_embeddings(job_ids: list[int]) -> dict[int, list[float]]:
    if not job_ids:
        return {}

    placeholders = ", ".join(f":job_id_{idx}" for idx, _ in enumerate(job_ids))
    params = {f"job_id_{idx}": job_id for idx, job_id in enumerate(job_ids)}

    with session_scope() as session:
        rows = session.exec(
            cast(
                Any,
                text(
                    f"""
                SELECT job_id, vector_json
                FROM job_embeddings
                WHERE job_id IN ({placeholders})
                """
                ),
            ),
            params=params,
        ).all()

    result: dict[int, list[float]] = {}
    for row in rows:
        mapping = row._mapping
        try:
            vector = json.loads(str(mapping["vector_json"] or "[]"))
        except json.JSONDecodeError:
            continue
        if isinstance(vector, list):
            result[int(mapping["job_id"])] = [float(value) for value in vector]
    return result


async def search_jobs_fts(user_query: str, limit: int) -> list[JobCandidate]:
    query = _build_match_query(user_query)
    if not query:
        return await fetch_recent_jobs(limit)

    with session_scope() as session:
        rows = session.exec(
            cast(
                Any,
                text(
                    """
                SELECT job_id, company, position, full_text, skills_text, bm25(jobs_fts) AS bm25_score
                FROM jobs_fts
                WHERE jobs_fts MATCH :query
                ORDER BY bm25_score ASC
                LIMIT :limit
                """
                ),
            ),
            params={"query": query, "limit": max(1, limit)},
        ).all()

    candidates: list[JobCandidate] = []
    for row in rows:
        mapping = row._mapping
        candidates.append(
            JobCandidate(
                job_id=int(mapping["job_id"]),
                company=str(mapping["company"] or "미상"),
                title=str(mapping["position"] or "미상"),
                content=str(mapping["full_text"] or ""),
                skills_text=str(mapping["skills_text"] or ""),
                bm25_score=float(mapping["bm25_score"] or 0.0),
            )
        )

    if candidates:
        return candidates
    return await fetch_recent_jobs(limit)


async def fetch_recent_jobs(limit: int) -> list[JobCandidate]:
    with session_scope() as session:
        rows = session.exec(
            cast(
                Any,
                text(
                    """
                SELECT id, company, position, full_text, skills_text
                FROM jobs
                ORDER BY updated_at DESC
                LIMIT :limit
                """
                ),
            ),
            params={"limit": max(1, limit)},
        ).all()

    candidates: list[JobCandidate] = []
    for row in rows:
        mapping = row._mapping
        candidates.append(
            JobCandidate(
                job_id=int(mapping["id"]),
                company=str(mapping["company"] or "미상"),
                title=str(mapping["position"] or "미상"),
                content=str(mapping["full_text"] or ""),
                skills_text=str(mapping["skills_text"] or ""),
                bm25_score=0.0,
            )
        )

    return candidates


async def fetch_job_detail(job_id: int) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="해당 공고를 찾을 수 없습니다.")

    return {
        "job_id": int(job.id or 0),
        "company": job.company,
        "title": job.position,
        "full_text": job.full_text,
        "skills_text": job.skills_text,
    }

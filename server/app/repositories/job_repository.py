from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import select

from server.app.db import session_scope
from server.app.models import Job, JobEmbedding

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣_+#.-]+")
POSITION_LINE_PATTERN = re.compile(r"^\[포지션\]\s*(.+)$", re.MULTILINE)
YEAR_TOKEN_PATTERN = re.compile(r"^\d+\s*년?$")
MATCH_QUERY_STOPWORDS = {"희망직무", "보유기술", "경력", "없음", "미입력", "년"}
ROLE_QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "backend": ("백엔드", "서버", "api"),
    "back-end": ("백엔드", "서버"),
    "백엔드": ("backend", "server", "api"),
    "frontend": ("프론트엔드", "웹"),
    "front-end": ("프론트엔드", "웹"),
    "프론트엔드": ("frontend", "front"),
    "data": ("데이터", "etl"),
    "데이터": ("data", "analytics"),
    "designer": ("디자이너", "ux", "ui"),
    "디자이너": ("designer", "ux", "ui"),
    "pm": ("기획", "product"),
    "po": ("기획", "product"),
    "마케터": ("marketing", "marketer"),
}

SQL_DELETE_FTS = "DELETE FROM jobs_fts WHERE job_id = :job_id"
SQL_INSERT_FTS = """
INSERT INTO jobs_fts (job_id, company, position, full_text, skills_text)
VALUES (:job_id, :company, :position, :full_text, :skills_text)
"""
SQL_SEARCH_FTS = """
SELECT job_id, company, position, full_text, skills_text, bm25(jobs_fts) AS bm25_score
FROM jobs_fts
WHERE jobs_fts MATCH :query
ORDER BY bm25_score ASC
LIMIT :limit
"""
SQL_RECENT_JOBS = """
SELECT id, company, position, full_text, skills_text
FROM jobs
ORDER BY updated_at DESC
LIMIT :limit
"""


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
        if token in MATCH_QUERY_STOPWORDS or key in MATCH_QUERY_STOPWORDS:
            continue
        if YEAR_TOKEN_PATTERN.fullmatch(token):
            continue
        if len(token) <= 1 and key not in {"c", "r"}:
            continue

        unique_tokens.append(token)
        seen.add(key)
        for expanded in ROLE_QUERY_EXPANSIONS.get(key, ()):
            expanded_key = expanded.lower()
            if expanded_key in seen:
                continue
            unique_tokens.append(expanded)
            seen.add(expanded_key)

    return " OR ".join(unique_tokens[:12])


def _exec_sql(session: Any, sql: str, params: dict[str, Any] | None = None) -> list[Any]:
    statement = cast(Any, text(sql))
    result = session.exec(statement, params=params or {})
    return list(result.all())


def _run_sql(session: Any, sql: str, params: dict[str, Any]) -> None:
    statement = cast(Any, text(sql))
    session.exec(statement, params=params)


def _row_to_candidate(row: Any, *, id_key: str, bm25_score: float) -> JobCandidate:
    mapping = cast(Mapping[str, Any], row._mapping)
    full_text = str(mapping.get("full_text") or "")
    return JobCandidate(
        job_id=int(mapping[id_key]),
        company=str(mapping.get("company") or "미상"),
        title=_resolve_position_title(mapping.get("position"), full_text),
        content=full_text,
        skills_text=str(mapping.get("skills_text") or ""),
        bm25_score=float(mapping.get("bm25_score") or bm25_score),
    )


def _build_in_clause(prefix: str, values: Sequence[int]) -> tuple[str, dict[str, int]]:
    placeholders = ", ".join(f":{prefix}_{idx}" for idx, _ in enumerate(values))
    params = {f"{prefix}_{idx}": int(value) for idx, value in enumerate(values)}
    return placeholders, params


def _resolve_position_title(raw_position: Any, full_text: str) -> str:
    position = str(raw_position or "").strip()
    if position and position != "미상":
        return position

    match = POSITION_LINE_PATTERN.search(full_text)
    if match:
        extracted = match.group(1).strip()
        if extracted:
            return extracted

    return "미상"


def _sync_jobs_fts(session: Any, job: Job) -> None:
    _run_sql(session, SQL_DELETE_FTS, {"job_id": job.id})
    _run_sql(
        session,
        SQL_INSERT_FTS,
        {
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

    placeholders, params = _build_in_clause("job_id", job_ids)
    sql = f"SELECT job_id, vector_json FROM job_embeddings WHERE job_id IN ({placeholders})"

    with session_scope() as session:
        rows = _exec_sql(session, sql, params=params)

    embeddings: dict[int, list[float]] = {}
    for row in rows:
        mapping = cast(Mapping[str, Any], row._mapping)
        try:
            vector = json.loads(str(mapping.get("vector_json") or "[]"))
        except json.JSONDecodeError:
            continue

        if isinstance(vector, list):
            embeddings[int(mapping["job_id"])] = [float(value) for value in vector]

    return embeddings


async def search_jobs_fts(user_query: str, limit: int) -> list[JobCandidate]:
    match_query = _build_match_query(user_query)
    if not match_query:
        return await fetch_recent_jobs(limit)

    with session_scope() as session:
        rows = _exec_sql(session, SQL_SEARCH_FTS, {"query": match_query, "limit": max(1, limit)})

    candidates = [_row_to_candidate(row, id_key="job_id", bm25_score=0.0) for row in rows]
    if candidates:
        return candidates

    return await fetch_recent_jobs(limit)


async def fetch_recent_jobs(limit: int) -> list[JobCandidate]:
    with session_scope() as session:
        rows = _exec_sql(session, SQL_RECENT_JOBS, {"limit": max(1, limit)})

    return [_row_to_candidate(row, id_key="id", bm25_score=0.0) for row in rows]


async def fetch_job_detail(job_id: int) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="해당 공고를 찾을 수 없습니다.")

    title = _resolve_position_title(job.position, job.full_text)
    return {
        "job_id": int(job.id or 0),
        "company": job.company,
        "title": title,
        "full_text": job.full_text,
        "skills_text": job.skills_text,
    }

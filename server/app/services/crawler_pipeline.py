from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from server.app.core.config import CRAWLER_FETCH_LIMIT, TARGET_JOB_GROUP, TARGET_JOB_ID, WANTED_BASE_URL
from server.app.crawlers.wanted import fetch_job_detail_raw, fetch_job_id_list
from server.app.repositories.job_repository import JobRecord, upsert_embedding, upsert_jobs
from server.app.services.embedding_service import embed_text

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CrawlResult:
    fetched: int
    upserted: int
    embedded: int


def _stringify_skills(raw_skills: Any) -> str:
    if not isinstance(raw_skills, list):
        return ""
    values: list[str] = []
    for item in raw_skills:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("text") or item.get("title") or "").strip()
            if name:
                values.append(name)
        else:
            text = str(item).strip()
            if text:
                values.append(text)

    deduplicated: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(value)

    return ", ".join(deduplicated)


def _build_full_text(job_data: dict[str, Any]) -> str:
    detail = job_data.get("detail") or {}
    company_name = (job_data.get("company") or {}).get("name", "미상")
    position = _extract_position(job_data)
    main_tasks = detail.get("main_tasks") or ""
    requirements = detail.get("requirements") or ""
    preferred = detail.get("preferred_points") or ""
    intro = detail.get("intro") or ""

    return "\n".join(
        [
            f"[회사] {company_name}",
            f"[포지션] {position}",
            f"[소개] {intro}",
            f"[주요업무] {main_tasks}",
            f"[자격요건] {requirements}",
            f"[우대사항] {preferred}",
        ]
    ).strip()


def _extract_position(job_data: dict[str, Any]) -> str:
    detail = job_data.get("detail") or {}
    return str(job_data.get("position") or detail.get("position") or "미상")


def _to_record(job_id: int, job_data: dict[str, Any]) -> JobRecord:
    company_name = (job_data.get("company") or {}).get("name") or "미상"
    position = _extract_position(job_data)
    skills_text = _stringify_skills(
        (job_data.get("skill_tags") or []) + (job_data.get("preferred_languages") or [])
    )

    return JobRecord(
        source="wanted",
        source_id=str(job_id),
        company=str(company_name),
        position=str(position),
        full_text=_build_full_text(job_data),
        skills_text=skills_text,
        collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


async def run_crawl_pipeline(limit: int | None = None) -> CrawlResult:
    """Wanted 크롤링부터 임베딩 저장까지 한 번에 수행한다."""
    fetch_limit = max(1, int(limit if limit is not None else CRAWLER_FETCH_LIMIT))
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": WANTED_BASE_URL,
    }

    records: list[JobRecord] = []

    with requests.Session() as session:
        session.headers.update(headers)
        job_ids = fetch_job_id_list(
            session=session,
            base_url=WANTED_BASE_URL,
            group_id=TARGET_JOB_GROUP,
            job_id=TARGET_JOB_ID,
            limit=fetch_limit,
        )

        for job_id in job_ids:
            detail = fetch_job_detail_raw(session, WANTED_BASE_URL, job_id)
            if detail:
                records.append(_to_record(job_id, detail))

    upserted_ids = await upsert_jobs(records)

    embedded_count = 0
    for job_id, record in zip(upserted_ids, records, strict=False):
        if not record.full_text:
            continue
        vector = await embed_text(record.full_text)
        await upsert_embedding(job_id, vector)
        embedded_count += 1

    logger.info(
        "crawl pipeline done: fetched=%s upserted=%s embedded=%s",
        len(records),
        len(upserted_ids),
        embedded_count,
    )
    return CrawlResult(fetched=len(records), upserted=len(upserted_ids), embedded=embedded_count)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_crawl_pipeline())

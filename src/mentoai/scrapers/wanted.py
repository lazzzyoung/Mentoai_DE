import asyncio
import logging
import random
from datetime import UTC, datetime
from typing import Any

import httpx

from mentoai.config import get_settings

logger = logging.getLogger(__name__)

LIST_API = "/api/chaos/navigation/v1/results"
DETAIL_API = "/api/chaos/jobs/v4/{job_id}/details"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


async def fetch_job_ids(
    client: httpx.AsyncClient, group_id: str, job_ids: str, max_items: int
) -> list[int]:
    ids: list[int] = []
    offset = 0
    while len(ids) < max_items:
        response = await client.get(
            LIST_API,
            params={
                "job_group_id": group_id,
                "job_ids": job_ids,
                "country": "kr",
                "job_sort": "job.popularity_order",
                "years": "-1",
                "locations": "all",
                "limit": "20",
                "offset": offset,
            },
        )
        if response.status_code != 200:
            logger.warning("wanted 리스트 요청 실패: %s", response.status_code)
            break
        data = response.json()
        jobs = data.get("data", [])
        if not jobs:
            break
        ids.extend(job["id"] for job in jobs if job.get("id") is not None)
        if not data.get("links", {}).get("next"):
            break
        offset += 20
        await asyncio.sleep(random.uniform(0.4, 0.8))
    return ids[:max_items]


async def fetch_detail(client: httpx.AsyncClient, job_id: int) -> dict[str, Any] | None:
    response = await client.get(DETAIL_API.format(job_id=job_id))
    if response.status_code == 404:
        logger.info("wanted 공고 삭제/비공개 (ID: %s)", job_id)
        return None
    if response.status_code != 200:
        logger.warning("wanted 상세 요청 실패: %s (ID: %s)", response.status_code, job_id)
        return None
    return response.json().get("data", {}).get("job") or None


async def scrape() -> list[dict[str, Any]]:
    """Wanted 공고를 수집해 bronze 레코드로 반환한다."""
    settings = get_settings()
    records: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=settings.wanted_base_url,
        headers={**HEADERS, "Referer": settings.wanted_base_url},
        timeout=15,
        follow_redirects=True,
    ) as client:
        ids = await fetch_job_ids(
            client,
            settings.wanted_job_group_id,
            settings.wanted_job_ids,
            settings.scrape_max_items,
        )
        logger.info("wanted: 수집 대상 %d건", len(ids))
        for job_id in ids:
            raw = await fetch_detail(client, job_id)
            if raw:
                records.append(
                    {
                        "source": "wanted",
                        "source_id": str(job_id),
                        "collected_at": datetime.now(UTC),
                        "payload": raw,
                    }
                )
            await asyncio.sleep(settings.scrape_delay_seconds + random.uniform(0, 0.3))
    return records

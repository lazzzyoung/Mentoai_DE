from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


def fetch_job_id_list(
    session: requests.Session,
    base_url: str,
    group_id: str,
    job_id: str,
    limit: int = 100,
) -> list[int]:
    """Wanted 리스트 API에서 공고 ID 목록을 수집한다."""
    job_ids: list[int] = []
    offset = 0
    api_url = f"{base_url}/api/chaos/navigation/v1/results"

    while True:
        params = {
            "country": "kr",
            "job_sort": "job.popularity_order",
            "years": "-1",
            "locations": "all",
            "limit": "20",
            "offset": offset,
        }
        if group_id:
            params["job_group_id"] = group_id
        if job_id:
            params["job_ids"] = job_id

        try:
            response = session.get(api_url, params=params, timeout=10)
        except requests.RequestException as error:
            logger.warning("Wanted 리스트 조회 실패: %s", error)
            break

        if response.status_code != 200:
            logger.warning("Wanted 리스트 응답 실패(status=%s)", response.status_code)
            break

        payload = response.json()
        jobs = payload.get("data", [])
        if not jobs:
            break

        for row in jobs:
            raw_id = row.get("id")
            if isinstance(raw_id, int):
                job_ids.append(raw_id)

        if len(job_ids) >= limit:
            return job_ids[:limit]

        if not payload.get("links", {}).get("next"):
            break

        offset += 20
        time.sleep(random.uniform(0.3, 0.8))

    return job_ids


def fetch_job_detail_raw(
    session: requests.Session, base_url: str, job_id: int
) -> dict[str, Any] | None:
    """Wanted 상세 API에서 단일 공고 원문을 가져온다."""
    timestamp = int(time.time() * 1000)
    target_url = f"{base_url}/api/chaos/jobs/v4/{job_id}/details?{timestamp}="

    try:
        response = session.get(target_url, timeout=10)
    except requests.RequestException as error:
        logger.warning("Wanted 상세 조회 실패(id=%s): %s", job_id, error)
        return None

    if response.status_code == 404:
        return None
    if response.status_code != 200:
        logger.warning("Wanted 상세 응답 실패(id=%s, status=%s)", job_id, response.status_code)
        return None

    return response.json().get("data", {}).get("job")

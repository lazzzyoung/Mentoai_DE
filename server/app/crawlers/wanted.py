from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20


def _build_list_params(group_id: str, job_id: str, offset: int) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "country": "kr",
        "job_sort": "job.popularity_order",
        "years": "-1",
        "locations": "all",
        "limit": str(_PAGE_SIZE),
        "offset": offset,
    }
    if group_id:
        params["job_group_id"] = group_id
    if job_id:
        params["job_ids"] = job_id
    return params


def _extract_job_ids(payload: dict[str, Any]) -> list[int]:
    jobs = payload.get("data", [])
    return [raw_id for row in jobs if isinstance((raw_id := row.get("id")), int)]


def _has_next_page(payload: dict[str, Any]) -> bool:
    return bool(payload.get("links", {}).get("next"))


def fetch_job_id_list(
    session: requests.Session,
    base_url: str,
    group_id: str,
    job_id: str,
    limit: int = 100,
) -> list[int]:
    """Wanted 리스트 API에서 공고 ID 목록을 수집한다."""
    api_url = f"{base_url}/api/chaos/navigation/v1/results"
    collected_ids: list[int] = []
    offset = 0

    while len(collected_ids) < limit:
        params = _build_list_params(group_id, job_id, offset)

        try:
            response = session.get(api_url, params=params, timeout=10)
        except requests.RequestException as error:
            logger.warning("Wanted 리스트 조회 실패: %s", error)
            break

        if response.status_code != 200:
            logger.warning("Wanted 리스트 응답 실패(status=%s)", response.status_code)
            break

        payload = response.json()
        job_ids = _extract_job_ids(payload)
        if not job_ids:
            break

        collected_ids.extend(job_ids)
        if not _has_next_page(payload):
            break

        offset += _PAGE_SIZE
        time.sleep(random.uniform(0.3, 0.8))

    return collected_ids[:limit]


def fetch_job_detail_raw(
    session: requests.Session,
    base_url: str,
    job_id: int,
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

    payload = response.json()
    return payload.get("data", {}).get("job")

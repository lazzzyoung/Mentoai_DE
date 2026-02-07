import logging
import random
import time

import requests

logger = logging.getLogger(__name__)


# 리스트 API를 순회, 공고 ID 목록 수집 함수
def fetch_job_id_list(session, base_url, group_id, job_id, limit=100):
    job_ids = []
    offset = 0
    api_url = f"{base_url}/api/chaos/navigation/v1/results"

    logger.info(f"ID 수집 시작 (Group: {group_id}, Job: {job_id})")

    while True:
        try:
            params = {
                "job_group_id": group_id,
                "job_ids": job_id,
                "country": "kr",
                "job_sort": "job.popularity_order",
                "years": "-1",
                "locations": "all",
                "limit": "20",
                "offset": offset,
            }

            # session 사용하여 연결 재사용
            response = session.get(api_url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"⚠️ 리스트 요청 실패 Code: {response.status_code}")
                break

            data_json = response.json()
            jobs = data_json.get("data", [])
            links = data_json.get("links", {})

            if not jobs:
                logger.info("더 이상 공고가 없습니다.")
                break

            # ID 추출
            current_ids = [job["id"] for job in jobs]
            job_ids.extend(current_ids)

            logger.info(f"   + {len(current_ids)}개 수집 (현재 누적: {len(job_ids)}개)")

            # 다음 페이지 확인
            if not links.get("next"):
                break

            if len(job_ids) >= limit:
                logger.info("설정된 제한(%s)에 도달하여 ID 수집을 중단합니다.", limit)
                break

            offset += 20

            # 봇 탐지 회피용
            time.sleep(random.uniform(0.5, 1.0))

        except requests.exceptions.Timeout:
            logger.error("⚠️ 리스트 요청 타임아웃. 잠시 대기 후 재시도 필요.")
            time.sleep(2)
            break
        except Exception as e:
            logger.error(f"⚠️ 리스트 수집 중 알 수 없는 에러: {e}")
            break

    return job_ids[:limit]


# 상세 API 호출 후 Raw Json 반환
def fetch_job_detail_raw(session, base_url, job_id):
    # Request URL에 현재 시간을 파라미터로 넣어 전송하기위해 작성
    timestamp = int(time.time() * 1000)
    target_url = f"{base_url}/api/chaos/jobs/v4/{job_id}/details?{timestamp}="

    try:
        response = session.get(target_url, timeout=10)

        if response.status_code == 200:
            return response.json().get("data", {}).get("job", {})
        elif response.status_code == 404:
            logger.warning(f"⚠️ 공고 삭제됨 또는 비공개 (ID: {job_id})")
            return None
        else:
            logger.warning(
                f"⚠️ 상세 요청 실패 Code: {response.status_code} (ID: {job_id})"
            )
            return None

    except requests.exceptions.Timeout:
        logger.error(f"⚠️ 상세 요청 타임아웃 (ID: {job_id})")
        return None
    except Exception as e:
        logger.error(f"⚠️ 상세 수집 중 에러 (ID: {job_id}): {e}")
        return None

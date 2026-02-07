import json
import logging
import os
import time

import requests
from dotenv import load_dotenv
from kafka import KafkaProducer
from kafka.errors import KafkaError

from utils.wanted_scraper import fetch_job_detail_raw, fetch_job_id_list

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("WANTED_BASE_URL", "https://www.wanted.co.kr")
GROUP_ID = os.getenv("TARGET_JOB_GROUP", "518")
JOB_ID_CODE = os.getenv("TARGET_JOB_ID", "655")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_NAME = os.getenv("KAFKA_TOPIC_NAME", "career_raw")
WANTED_LIMIT = int(os.getenv("WANTED_LIMIT", "50"))


def _create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=[BOOTSTRAP_SERVERS],
        value_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda value: str(value).encode("utf-8"),
        retries=3,
    )


def run_producer() -> None:
    logger.info("Wanted producer 시작 | bootstrap=%s topic=%s", BOOTSTRAP_SERVERS, TOPIC_NAME)

    try:
        producer = _create_producer()
    except Exception as exc:
        logger.critical("Kafka 연결 실패: %s", exc)
        return

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": BASE_URL,
            }
        )

        target_ids = fetch_job_id_list(
            session=session,
            base_url=BASE_URL,
            group_id=GROUP_ID,
            job_id=JOB_ID_CODE,
            limit=WANTED_LIMIT,
        )

        if not target_ids:
            logger.warning("수집된 공고 ID가 없습니다.")
            producer.close()
            return

        logger.info("총 %s개의 공고 상세 정보 수집을 시작합니다.", len(target_ids))

        success_count = 0
        fail_count = 0
        for job_id in target_ids[:WANTED_LIMIT]:
            try:
                raw_data = fetch_job_detail_raw(session, BASE_URL, job_id)
                if not raw_data:
                    fail_count += 1
                    continue

                message = {
                    "source": "wanted",
                    "source_id": str(job_id),
                    "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "raw_data": raw_data,
                }

                producer.send(TOPIC_NAME, key=str(job_id), value=message)
                success_count += 1

                if success_count % 10 == 0:
                    logger.info("%s건 전송 완료", success_count)

                time.sleep(0.5)
            except KafkaError as exc:
                logger.error("Kafka 전송 에러 (id=%s): %s", job_id, exc)
                fail_count += 1
            except Exception as exc:
                logger.error("알 수 없는 에러 (id=%s): %s", job_id, exc)
                fail_count += 1

    producer.flush()
    producer.close()
    logger.info("Wanted producer 완료 | 성공=%s 실패=%s", success_count, fail_count)


if __name__ == "__main__":
    run_producer()

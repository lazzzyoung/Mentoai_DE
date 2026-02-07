import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from kafka import KafkaProducer

from utils.recruit24_parser import build_job_message, parse_list_row
from utils.recruit24_scraper import fetch_job_list, get_detail_info

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TOPIC_NAME = os.getenv("KAFKA_TOPIC_NAME", "career_raw")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
MAX_JOBS_PER_RUN = int(os.getenv("RECRUIT24_DAILY_LIMIT", "50"))


def _create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=[BOOTSTRAP_SERVERS],
        value_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode(
            "utf-8"
        ),
    )


def _iter_daily_rows() -> list[Any]:
    rows = fetch_job_list(page_index=1)
    return rows[:MAX_JOBS_PER_RUN] if rows else []


def run_daily_producer() -> None:
    rows = _iter_daily_rows()
    if not rows:
        logger.warning("공고를 가져오지 못했습니다.")
        return

    producer = _create_producer()
    sent_count = 0

    try:
        logger.info(
            "[Daily] 최신 공고 수집 시작 | bootstrap=%s topic=%s limit=%s",
            BOOTSTRAP_SERVERS,
            TOPIC_NAME,
            MAX_JOBS_PER_RUN,
        )

        for index, row in enumerate(rows, start=1):
            parsed = parse_list_row(row)
            if not parsed:
                logger.info("[%s/%s] 파싱 실패로 skip", index, len(rows))
                continue

            detail = get_detail_info(parsed["auth_no"])
            message = build_job_message(parsed, detail)

            producer.send(
                TOPIC_NAME,
                key=parsed["auth_no"].encode("utf-8"),
                value=message,
            )
            sent_count += 1
            logger.info(
                "[%s/%s] 전송 완료 id=%s company=%s",
                index,
                len(rows),
                parsed["auth_no"],
                parsed["company"][:10],
            )
    finally:
        producer.flush()
        producer.close()

    logger.info("Daily producer 완료: %s건 전송", sent_count)


if __name__ == "__main__":
    run_daily_producer()

import argparse
import json
import logging
import os
import random
import time

from dotenv import load_dotenv
from kafka import KafkaProducer

from utils.recruit24_parser import build_job_message, parse_list_row
from utils.recruit24_scraper import fetch_job_list, get_detail_info

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


def resolve_topic_name() -> str:
    return os.getenv("KAFKA_BACKFILL_TOPIC") or os.getenv(
        "KAFKA_TOPIC_NAME", "career_raw"
    )


TOPIC_NAME = resolve_topic_name()


def _create_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=[BOOTSTRAP_SERVERS],
        value_serializer=lambda payload: json.dumps(payload, ensure_ascii=False).encode(
            "utf-8"
        ),
        linger_ms=20,
        batch_size=16384,
    )


def _process_page(producer: KafkaProducer, page: int, end_page: int) -> int:
    rows = fetch_job_list(page_index=page)
    if not rows:
        logger.warning("[Page %s/%s] 로딩 실패 또는 데이터 없음", page, end_page)
        return 0

    page_count = 0
    for row in rows:
        parsed = parse_list_row(row)
        if not parsed:
            continue

        detail = get_detail_info(parsed["auth_no"])
        message = build_job_message(parsed, detail)

        producer.send(
            TOPIC_NAME,
            key=parsed["auth_no"].encode("utf-8"),
            value=message,
        )
        page_count += 1

    producer.flush()
    logger.info("[Page %s/%s] %s건 전송", page, end_page, page_count)
    return page_count


def run_backfill(start_page: int, end_page: int) -> None:
    if start_page > end_page:
        raise ValueError("start_page must be less than or equal to end_page")

    producer = _create_producer()
    total_count = 0

    try:
        logger.info(
            "Backfill 시작 | bootstrap=%s topic=%s range=%s-%s",
            BOOTSTRAP_SERVERS,
            TOPIC_NAME,
            start_page,
            end_page,
        )

        for page in range(start_page, end_page + 1):
            total_count += _process_page(producer, page, end_page)
            time.sleep(random.uniform(2.0, 4.0))
    finally:
        producer.close()

    logger.info("Backfill 완료: %s건 전송", total_count)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recruit24 backfill producer")
    parser.add_argument("start_page", nargs="?", default=1, type=int)
    parser.add_argument("end_page", nargs="?", default=2, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_backfill(args.start_page, args.end_page)

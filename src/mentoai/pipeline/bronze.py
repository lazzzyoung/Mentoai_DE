import logging
from collections.abc import Awaitable, Callable
from typing import Any

from mentoai.db.pool import executemany
from mentoai.scrapers import wanted, work24

logger = logging.getLogger(__name__)

Scraper = Callable[[], Awaitable[list[dict[str, Any]]]]

SCRAPERS: tuple[Scraper, ...] = (wanted.scrape, work24.scrape)

UPSERT_SQL = """
INSERT INTO bronze.raw_postings (source, source_id, payload, collected_at)
VALUES ($1, $2, $3, $4)
ON CONFLICT (source, source_id)
DO UPDATE SET payload = EXCLUDED.payload, collected_at = EXCLUDED.collected_at
"""


async def run() -> int:
    records: list[dict[str, Any]] = []
    for scraper in SCRAPERS:
        try:
            records.extend(await scraper())
        except Exception as error:  # 한 소스 실패가 전체 파이프라인을 죽이지 않는다
            logger.error("scraper %s 실패: %s", scraper.__module__, error)
    if not records:
        logger.warning("bronze: 수집된 레코드 없음")
        return 0

    await executemany(
        UPSERT_SQL,
        [(r["source"], r["source_id"], r["payload"], r["collected_at"]) for r in records],
    )
    logger.info("bronze upsert: %d건", len(records))
    return len(records)

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from server.app.core.config import CRAWLER_INTERVAL_MINUTES
from server.app.services.crawler_pipeline import run_crawl_pipeline

logger = logging.getLogger(__name__)


async def _run_job() -> None:
    result = await run_crawl_pipeline()
    logger.info("scheduler job result: %s", result)


def _run_job_sync() -> None:
    asyncio.run(_run_job())


def start_scheduler() -> None:
    """APScheduler를 사용해 크롤러 파이프라인을 주기 실행한다."""
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        _run_job_sync,
        trigger="interval",
        minutes=max(1, CRAWLER_INTERVAL_MINUTES),
        id="crawl_pipeline",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    logger.info("crawler scheduler started: interval=%smin", CRAWLER_INTERVAL_MINUTES)
    scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_scheduler()

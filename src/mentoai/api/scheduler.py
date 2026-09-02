import logging
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from mentoai.config import get_settings

logger = logging.getLogger(__name__)

JOB_ID = "mentoai_pipeline"

_scheduler: AsyncIOScheduler | None = None


def set_active_scheduler(scheduler: AsyncIOScheduler | None) -> None:
    global _scheduler
    _scheduler = scheduler


def schedule_info() -> dict[str, Any]:
    """현재 스케줄 상태. 실행 중이면 실제 다음 실행시각, 아니면 cron 계산값."""
    settings = get_settings()
    info: dict[str, Any] = {
        "enabled": settings.schedule_enabled,
        "cron": settings.schedule_cron,
        "timezone": settings.schedule_timezone,
        "next_run": None,
    }
    if not settings.schedule_enabled:
        return info

    if _scheduler is not None:
        job = _scheduler.get_job(JOB_ID)
        if job is not None and job.next_run_time is not None:
            info["next_run"] = job.next_run_time.isoformat()
            return info

    trigger = CronTrigger.from_crontab(settings.schedule_cron, timezone=settings.schedule_timezone)
    next_run = trigger.get_next_fire_time(None, datetime.now(UTC))
    if next_run is not None:
        info["next_run"] = next_run.isoformat()
    return info


async def start_scheduler() -> AsyncIOScheduler | None:
    """SCHEDULE_ENABLED=true일 때만 파이프라인 cron 스케줄러를 띄운다."""
    settings = get_settings()
    if not settings.schedule_enabled:
        return None

    from mentoai.pipeline.runner import run_pipeline

    scheduler = AsyncIOScheduler(timezone=settings.schedule_timezone)
    scheduler.add_job(
        run_pipeline,
        CronTrigger.from_crontab(settings.schedule_cron, timezone=settings.schedule_timezone),
        id=JOB_ID,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    set_active_scheduler(scheduler)
    logger.info("스케줄러 시작: %s (%s)", settings.schedule_cron, settings.schedule_timezone)
    return scheduler

import logging

from mentoai.db.pool import execute, fetchrow
from mentoai.pipeline import bronze, gold, silver

logger = logging.getLogger(__name__)


async def _start_run() -> int:
    row = await fetchrow("INSERT INTO pipeline_runs DEFAULT VALUES RETURNING id")
    assert row is not None
    return row["id"]


async def _finish_run(
    run_id: int,
    scraped: int,
    silver_upserted: int,
    embedded: int,
    status: str,
    error: str | None = None,
) -> None:
    await execute(
        """
        UPDATE pipeline_runs
        SET finished_at = now(), scraped = $2, silver_upserted = $3,
            embedded = $4, status = $5, error = $6
        WHERE id = $1
        """,
        run_id, scraped, silver_upserted, embedded, status, error,
    )


async def run_pipeline() -> dict[str, int]:
    """bronze -> silver -> gold 전체 파이프라인 실행."""
    run_id = await _start_run()
    try:
        scraped = await bronze.run()
        silver_upserted = await silver.run()
        embedded = await gold.run()
    except Exception as error:
        logger.exception("파이프라인 실패")
        await _finish_run(run_id, 0, 0, 0, "failed", str(error))
        raise
    await _finish_run(run_id, scraped, silver_upserted, embedded, "success")
    result = {
        "scraped": scraped,
        "silver_upserted": silver_upserted,
        "embedded": embedded,
    }
    logger.info("파이프라인 완료: %s", result)
    return result

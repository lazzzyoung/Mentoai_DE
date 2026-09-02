import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from mentoai import ops
from mentoai.db.pool import fetchrow
from mentoai.ops import UserPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _not_found(error: KeyError) -> HTTPException:
    detail = error.args[0] if error.args else "찾을 수 없습니다"
    return HTTPException(status_code=404, detail=detail)



@router.get("/stats")
async def stats() -> dict[str, Any]:
    return await ops.get_status()


@router.get("/pipeline-runs")
async def pipeline_runs() -> list[dict[str, Any]]:
    return await ops.list_runs()


@router.post("/pipeline")
async def trigger_pipeline() -> dict[str, str]:
    from mentoai.pipeline.runner import run_pipeline

    running = await fetchrow(
        "SELECT id FROM pipeline_runs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
    )
    if running:
        raise HTTPException(status_code=409, detail="파이프라인이 이미 실행 중입니다")
    if not ops.start_background("pipeline", run_pipeline):
        raise HTTPException(status_code=409, detail="동일 작업이 이미 실행 중입니다")
    logger.info("어드민 요청으로 파이프라인 즉시 실행")
    return {"status": "started"}


@router.get("/jobs")
async def jobs_list(query: str = "", limit: int = 30) -> list[dict[str, Any]]:
    return await ops.list_jobs(query, limit)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: int) -> None:
    try:
        await ops.delete_job(job_id)
    except KeyError as error:
        raise _not_found(error) from error


@router.post("/users", status_code=201)
async def create_user(payload: UserPayload) -> dict[str, Any]:
    try:
        return await ops.create_user(payload)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/users/{user_id}")
async def update_user(user_id: int, payload: UserPayload) -> dict[str, Any]:
    try:
        return await ops.update_user(user_id, payload)
    except KeyError as error:
        raise _not_found(error) from error


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int) -> None:
    try:
        await ops.delete_user(user_id)
    except KeyError as error:
        raise _not_found(error) from error


@router.get("/embedding/models")
async def embedding_models() -> dict[str, Any]:
    return ops.embedding_models()


@router.post("/embedding/rebuild")
async def rebuild_embeddings() -> dict[str, Any]:
    if not ops.start_background("embedding_rebuild", ops.rebuild_embeddings):
        raise HTTPException(status_code=409, detail="이미 실행 중입니다")
    return {"status": "started"}


@router.post("/embedding/switch")
async def switch_embedding(provider: str, model: str | None = None) -> dict[str, Any]:
    from mentoai.embed_switch import resolve_target

    try:
        target = resolve_target(provider, model, None)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    if not ops.start_background(
        "embedding_switch", lambda: ops.switch_embedding_model(provider, model)
    ):
        raise HTTPException(status_code=409, detail="이미 실행 중입니다")
    logger.info("어드민 요청으로 임베딩 모델 전환: %s:%s", target.provider, target.model)
    return {"status": "started", "target": f"{target.provider}:{target.model}", "dim": target.dim}


@router.get("/cache")
async def cache_list() -> list[dict[str, Any]]:
    return await ops.list_cache()


@router.delete("/cache")
async def cache_clear() -> dict[str, int]:
    return {"deleted": await ops.clear_cache()}


@router.delete("/cache/{job_id}/{user_id}", status_code=204)
async def cache_delete(job_id: int, user_id: int) -> None:
    try:
        await ops.delete_cache(job_id, user_id)
    except KeyError as error:
        raise _not_found(error) from error

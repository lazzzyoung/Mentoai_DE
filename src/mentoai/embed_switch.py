"""임베딩 모델 한 방 전환: 검증 → .env 갱신(백업) → 테이블 재생성 → 전량 재임베딩."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from mentoai.config import get_settings

logger = logging.getLogger(__name__)

FASTEMBED_DEFAULT = "intfloat/multilingual-e5-large"
GEMINI_DEFAULT = "gemini-embedding-001"
GEMINI_DEFAULT_DIM = 1024
PROVIDERS = ("fastembed", "gemini")


@dataclass(frozen=True)
class TargetSpec:
    provider: str
    model: str
    dim: int


def fastembed_dim(model: str) -> int:
    """fastembed 지원 목록에서 실제 차원을 조회한다 (지원 여부 검증 겸용)."""
    from fastembed import TextEmbedding

    for info in TextEmbedding.list_supported_models():
        if info["model"] == model:
            return int(info["dim"])
    raise ValueError(f"fastembed이 지원하지 않는 모델: {model} (`mentoai models`로 목록 확인)")


def resolve_target(provider: str, model: str | None, dim: int | None) -> TargetSpec:
    provider = provider.lower()
    if provider not in PROVIDERS:
        raise ValueError(f"알 수 없는 provider: {provider} (fastembed | gemini)")
    if provider == "gemini":
        return TargetSpec(provider, model or GEMINI_DEFAULT, dim or GEMINI_DEFAULT_DIM)
    resolved_model = model or FASTEMBED_DEFAULT
    return TargetSpec(provider, resolved_model, dim or fastembed_dim(resolved_model))


async def switch_embedding(
    provider: str,
    model: str | None = None,
    dim: int | None = None,
    env_file: str | Path = ".env",
) -> dict:
    from mentoai.envfile import env_file_has_key, update_env_file

    target = resolve_target(provider, model, dim)
    env_path = Path(env_file)

    # Gemini 전환 시 API 키 사전 확인 (환경변수 또는 기존 .env)
    if target.provider == "gemini" and not (
        os.environ.get("GOOGLE_API_KEY") or env_file_has_key(env_path, "GOOGLE_API_KEY")
    ):
        raise ValueError("GOOGLE_API_KEY가 없습니다. .env에 먼저 설정하세요.")

    # .env 갱신(주석 보존 + 백업) 후 프로세스 설정도 즉시 동기화
    settings = get_settings()
    updates = {
        "EMBEDDING_PROVIDER": target.provider,
        "EMBEDDING_DIM": str(target.dim),
        "EMBEDDING_MODEL": (
            target.model if target.provider == "fastembed" else settings.embedding_model
        ),
        "GEMINI_EMBEDDING_MODEL": (
            target.model if target.provider == "gemini" else settings.gemini_embedding_model
        ),
    }
    backup_path = update_env_file(env_path, updates)
    for key, value in updates.items():
        os.environ[key] = value
    get_settings.cache_clear()

    from mentoai.ai.embeddings import reset_model
    from mentoai.db.migrate import recreate_job_embeddings
    from mentoai.pipeline import gold

    reset_model()
    # 임베딩은 파생 데이터: 차원/모델 무관하게 테이블 재생성 후 전량 재임베딩
    await recreate_job_embeddings(target.dim)
    embedded = await gold.run()

    result = {
        "provider": target.provider,
        "model": target.model,
        "dim": target.dim,
        "re_embedded": embedded,
        "env_backup": str(backup_path) if backup_path else None,
    }
    logger.info("임베딩 모델 전환 완료: %s", result)
    return result

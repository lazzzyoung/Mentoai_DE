import pytest

from mentoai.ai.embeddings import model_key
from mentoai.embed_switch import PROVIDERS, resolve_target
from mentoai.envfile import env_file_has_key, update_env_file
from mentoai.pipeline.gold import PENDING_SQL


def test_update_env_file_preserves_comments_and_order(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# 상단 주석\nDATABASE_URL=postgres://old\n\n# 임베딩 섹션\nEMBEDDING_MODEL=old-model\n",
        encoding="utf-8",
    )

    backup = update_env_file(env, {"EMBEDDING_MODEL": "new-model", "EMBEDDING_PROVIDER": "gemini"})

    content = env.read_text(encoding="utf-8")
    assert "# 상단 주석" in content
    assert "DATABASE_URL=postgres://old" in content
    assert "EMBEDDING_MODEL=new-model" in content
    assert "EMBEDDING_PROVIDER=gemini" in content
    # 기존 키는 제자리에서 교체, 새 키는 끝에 추가
    assert content.index("DATABASE_URL") < content.index("EMBEDDING_MODEL=new-model")
    assert backup is not None and backup.exists()
    assert "EMBEDDING_MODEL=old-model" in backup.read_text(encoding="utf-8")


def test_update_env_file_creates_missing_file(tmp_path) -> None:
    env = tmp_path / ".env"
    backup = update_env_file(env, {"EMBEDDING_PROVIDER": "fastembed"}, backup=True)
    assert env.read_text(encoding="utf-8").strip() == "EMBEDDING_PROVIDER=fastembed"
    assert backup is None  # 원본이 없으면 백업도 없음


def test_env_file_has_key(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("# GOOGLE_API_KEY=주석이라무시\nGOOGLE_API_KEY=real\n", encoding="utf-8")
    assert env_file_has_key(env, "GOOGLE_API_KEY") is True
    assert env_file_has_key(env, "MISSING_KEY") is False


def test_resolve_target_fastembed_default() -> None:
    target = resolve_target("fastembed", None, None)
    assert target.model == "intfloat/multilingual-e5-large"
    assert target.dim == 1024  # fastembed 지원 목록에서 실제 차원 조회


def test_resolve_target_fastembed_validates_model() -> None:
    with pytest.raises(ValueError, match="fastembed이 지원하지 않는"):
        resolve_target("fastembed", "BAAI/bge-m3", None)  # 지원 목록에 없음


def test_resolve_target_gemini_default() -> None:
    target = resolve_target("gemini", None, None)
    assert target.model == "gemini-embedding-001"
    assert target.dim == 1024


def test_resolve_target_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="알 수 없는 provider"):
        resolve_target("openai", None, None)
    assert PROVIDERS == ("fastembed", "gemini")


def test_model_key_distinguishes_provider(monkeypatch) -> None:
    from types import SimpleNamespace

    from mentoai.ai import embeddings

    def stub(**overrides):
        base = {
            "embedding_provider": "fastembed",
            "embedding_model": "intfloat/multilingual-e5-large",
            "gemini_embedding_model": "gemini-embedding-001",
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    monkeypatch.setattr(embeddings, "get_settings", lambda: stub())
    assert model_key() == "fastembed:intfloat/multilingual-e5-large"
    monkeypatch.setattr(
        embeddings, "get_settings", lambda: stub(embedding_provider="gemini")
    )
    assert model_key() == "gemini:gemini-embedding-001"


def test_gold_sql_self_heals_on_model_change() -> None:
    """모델 컬럼이 다르면 파이프라인이 자동으로 재임베딩한다."""
    assert "e.model <> $1" in PENDING_SQL

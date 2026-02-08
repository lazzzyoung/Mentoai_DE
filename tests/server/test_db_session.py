import importlib
import sys
from pathlib import Path


def _normalize(url: str) -> str:
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    module = importlib.import_module("server.app.db.session")
    return module.normalize_database_url(url)


def test_normalize_database_url_converts_postgresql_scheme() -> None:
    normalized = _normalize("postgresql://user:pw@localhost:5432/mentoai")
    assert normalized == "postgresql+asyncpg://user:pw@localhost:5432/mentoai"


def test_normalize_database_url_converts_legacy_postgres_scheme() -> None:
    normalized = _normalize("postgres://user:pw@localhost:5432/mentoai")
    assert normalized == "postgresql+asyncpg://user:pw@localhost:5432/mentoai"


def test_normalize_database_url_converts_psycopg2_driver() -> None:
    normalized = _normalize("postgresql+psycopg2://user:pw@localhost:5432/mentoai")
    assert normalized == "postgresql+asyncpg://user:pw@localhost:5432/mentoai"


def test_normalize_database_url_keeps_asyncpg_driver() -> None:
    normalized = _normalize("postgresql+asyncpg://user:pw@localhost:5432/mentoai")
    assert normalized == "postgresql+asyncpg://user:pw@localhost:5432/mentoai"

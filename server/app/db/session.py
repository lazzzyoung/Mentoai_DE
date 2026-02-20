from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from sqlmodel import Session, SQLModel, create_engine

import server.app.models  # noqa: F401
from server.app.core.config import SQLITE_DB_PATH

_engine = None
_initialized = False
_init_lock = Lock()


# FTS5는 SQLModel 메타데이터 외부라 별도 SQL로 관리한다.
FTS_INIT_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts
USING fts5(
  job_id UNINDEXED,
  company,
  position,
  full_text,
  skills_text
)
"""


PRAGMA_SQL = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
)


def _build_sqlite_url() -> str:
    raw_path = os.getenv("SQLITE_DB_PATH", str(SQLITE_DB_PATH))
    path = Path(raw_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def get_engine():
    global _engine

    if _engine is None:
        _engine = create_engine(
            _build_sqlite_url(),
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def init_db() -> None:
    global _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        engine = get_engine()
        SQLModel.metadata.create_all(engine)
        with engine.begin() as conn:
            for pragma in PRAGMA_SQL:
                conn.exec_driver_sql(pragma)
            conn.exec_driver_sql(FTS_INIT_SQL)
        _initialized = True


@contextmanager
def session_scope() -> Iterator[Session]:
    init_db()
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()


def close_engine() -> None:
    global _engine, _initialized

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _initialized = False


def reset_db_for_tests(db_path: str) -> None:
    """테스트용: DB 경로를 바꾸고 엔진 상태를 초기화한다."""
    os.environ["SQLITE_DB_PATH"] = db_path
    close_engine()

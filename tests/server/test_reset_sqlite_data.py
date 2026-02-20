from pathlib import Path

from server.app.scripts.reset_sqlite_data import (
    SQLITE_SIDE_SUFFIXES,
    reset_sqlite_files,
)


def test_reset_sqlite_files_removes_db_and_sidecars(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "reset_target.db"
    db_path.write_text("db")

    sidecars = [Path(f"{db_path}{suffix}") for suffix in SQLITE_SIDE_SUFFIXES]
    for sidecar in sidecars:
        sidecar.write_text("side")

    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    result = reset_sqlite_files()

    assert result == 0
    assert not db_path.exists()
    assert all(not sidecar.exists() for sidecar in sidecars)

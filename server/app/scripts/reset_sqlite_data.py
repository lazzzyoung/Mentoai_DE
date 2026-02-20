from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from server.app.db.session import close_engine

SQLITE_SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


def resolve_sqlite_path() -> Path:
    load_dotenv()

    raw_path = os.getenv("SQLITE_DB_PATH", "./data/mentoai.db")
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    else:
        db_path = db_path.resolve()
    return db_path


def build_delete_targets(db_path: Path) -> list[Path]:
    targets = [db_path]
    targets.extend(Path(f"{db_path}{suffix}") for suffix in SQLITE_SIDE_SUFFIXES)
    return targets


def reset_sqlite_files() -> int:
    close_engine()
    db_path = resolve_sqlite_path()
    targets = build_delete_targets(db_path)

    removed: list[Path] = []
    missing: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for target in targets:
        try:
            if target.exists():
                target.unlink()
                removed.append(target)
            else:
                missing.append(target)
        except OSError as error:
            failed.append((target, str(error)))

    print(f"SQLite 기준 경로: {db_path}")
    if removed:
        print("삭제된 파일:")
        for path in removed:
            print(f"- {path}")
    if missing:
        print("원래 없던 파일:")
        for path in missing:
            print(f"- {path}")
    if failed:
        print("삭제 실패:")
        for path, reason in failed:
            print(f"- {path}: {reason}")
        print("실패 파일이 있어 종료 코드 1로 종료합니다. 서버/스케줄러를 먼저 중지해 주세요.")
        return 1

    print("데이터 리셋 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(reset_sqlite_files())

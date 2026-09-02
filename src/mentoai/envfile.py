"""줄 보존 방식의 .env 업데이트 (주석·순서·기타 키 유지, 자동 백업)."""

import shutil
from pathlib import Path


def update_env_file(path: Path, updates: dict[str, str], backup: bool = True) -> Path | None:
    """키가 이미 있으면 해당 줄만 교체, 없으면 파일 끝에 추가. 백업 경로를 반환."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    backup_path: Path | None = None
    if backup and path.exists():
        backup_path = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup_path)

    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return backup_path


def env_file_has_key(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#") and "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            return True
    return False

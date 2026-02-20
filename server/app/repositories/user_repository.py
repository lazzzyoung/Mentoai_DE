from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlmodel import select

from server.app.db import close_engine, session_scope
from server.app.models import User, UserSpec


def _normalize_user_name(user_name: str) -> str:
    name = (user_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름은 필수 입력 항목입니다.")
    return name


def _normalize_skills(skills: list[str]) -> list[str]:
    return [skill.strip() for skill in skills if skill and skill.strip()]


def _parse_skills(skills_json: str | None) -> list[str]:
    if not skills_json:
        return []
    try:
        data = json.loads(skills_json)
        if isinstance(data, list):
            return [str(skill).strip() for skill in data if str(skill).strip()]
    except json.JSONDecodeError:
        return []
    return []


async def fetch_user_info(user_id: int) -> dict[str, Any]:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")

        spec_stmt = select(UserSpec).where(UserSpec.user_id == user_id)
        spec = session.exec(spec_stmt).first()

    return {
        "username": user.username,
        "desired_job": spec.desired_job if spec else "미입력",
        "career_years": spec.career_years if spec else 0,
        "skills": _parse_skills(spec.skills_json if spec else "[]"),
    }


async def create_quick_user(
    user_name: str,
    desired_job: str,
    career_years: int,
    skills: list[str],
) -> int:
    name = _normalize_user_name(user_name)
    normalized_job = (desired_job or "미입력").strip() or "미입력"
    normalized_skills = _normalize_skills(skills)

    try:
        career_years_int = int(career_years)
        if career_years_int < 0:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="경력(년)은 0 이상의 숫자로 입력해 주세요.",
        ) from error

    with session_scope() as session:
        user_stmt = select(User).where(User.username == name)
        user = session.exec(user_stmt).first()

        if user is None:
            user = User(username=name)
            session.add(user)
            session.commit()
            session.refresh(user)

        if user.id is None:
            raise HTTPException(
                status_code=500,
                detail="계정을 생성하는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            )

        user_id = int(user.id)
        spec_stmt = select(UserSpec).where(UserSpec.user_id == user_id)
        spec = session.exec(spec_stmt).first()

        if spec is None:
            spec = UserSpec(
                user_id=user_id,
                desired_job=normalized_job,
                career_years=career_years_int,
                skills_json=json.dumps(normalized_skills, ensure_ascii=False),
            )
            session.add(spec)
        else:
            spec.desired_job = normalized_job
            spec.career_years = career_years_int
            spec.skills_json = json.dumps(normalized_skills, ensure_ascii=False)
            spec.updated_at = datetime.now(UTC)

        session.commit()
        return user_id


async def close_pool() -> None:
    close_engine()

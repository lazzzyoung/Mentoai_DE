from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=80)
    created_at: datetime = Field(default_factory=utc_now)


class UserSpec(SQLModel, table=True):
    __tablename__ = "user_specs"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True, foreign_key="users.id")
    desired_job: str = Field(default="미입력", max_length=120)
    career_years: int = Field(default=0)
    skills_json: str = Field(default="[]", max_length=4000)
    updated_at: datetime = Field(default_factory=utc_now)

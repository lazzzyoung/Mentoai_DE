from datetime import datetime

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str
    email: str
    created_at: datetime | None = None


class UserSpec(SQLModel, table=True):
    __tablename__ = "user_specs"

    spec_id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    desired_job: str | None = None
    career_years: int = 0
    education: str | None = None
    skills: list[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    certificates: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String)),
    )
    updated_at: datetime | None = None

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_jobs_source_source_id"),)

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(default="wanted", index=True, max_length=40)
    source_id: str = Field(index=True, max_length=120)
    company: str = Field(default="미상", max_length=255)
    position: str = Field(default="미상", max_length=255)
    full_text: str = Field(default="", max_length=20000)
    skills_text: str = Field(default="", max_length=2000)
    collected_at: str = Field(default="")
    updated_at: datetime = Field(default_factory=utc_now)


class JobEmbedding(SQLModel, table=True):
    __tablename__ = "job_embeddings"

    job_id: int = Field(primary_key=True, foreign_key="jobs.id")
    vector_json: str = Field(default="[]", max_length=50000)
    updated_at: datetime = Field(default_factory=utc_now)

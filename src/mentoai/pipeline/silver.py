import asyncio
import logging
import re
from typing import Any

import polars as pl

from mentoai.db.pool import executemany, fetch

logger = logging.getLogger(__name__)

COLUMNS = [
    "source",
    "source_id",
    "company",
    "position",
    "location",
    "intro",
    "main_tasks",
    "requirements",
    "preferred_points",
    "benefits",
    "employment_type",
    "is_newbie",
    "annual_from",
    "annual_to",
    "due_time",
    "skill_tags",
    "pay",
    "link",
    "deadline",
    "collected_at",
]

# 스키마를 명시한다: from_dicts 기본 추론이 첫 100행만 보는데,
# 소스별로 채워지는 컬럼이 달라(Wanted는 pay=NULL, work24는 문자열) 실데이터에서 타입 충돌이 난다.
SCHEMA = {
    "source": pl.String,
    "source_id": pl.String,
    "company": pl.String,
    "position": pl.String,
    "location": pl.String,
    "intro": pl.String,
    "main_tasks": pl.String,
    "requirements": pl.String,
    "preferred_points": pl.String,
    "benefits": pl.String,
    "employment_type": pl.String,
    "is_newbie": pl.Boolean,
    "annual_from": pl.Int64,
    "annual_to": pl.Int64,
    "due_time": pl.String,
    "skill_tags": pl.List(pl.String),
    "pay": pl.String,
    "link": pl.String,
    "deadline": pl.String,
    "collected_at": pl.Datetime("us", "UTC"),
}


def clean_text(value: Any) -> str | None:
    """HTML 태그 제거 + 공백 정규화. 비면 None."""
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def normalize_wanted(record: dict[str, Any]) -> dict[str, Any] | None:
    payload = record["payload"]
    detail = payload.get("detail") or {}
    source_id = str(payload.get("id") or record.get("source_id") or "")
    if not source_id:
        return None
    return {
        "source": "wanted",
        "source_id": source_id,
        "company": clean_text((payload.get("company") or {}).get("name")),
        "position": clean_text(detail.get("position")),
        "location": clean_text((payload.get("address") or {}).get("full_location")),
        "intro": clean_text(detail.get("intro")),
        "main_tasks": clean_text(detail.get("main_tasks")),
        "requirements": clean_text(detail.get("requirements")),
        "preferred_points": clean_text(detail.get("preferred_points")),
        "benefits": clean_text(detail.get("benefits")),
        "employment_type": clean_text(payload.get("employment_type")),
        "is_newbie": payload.get("is_newbie"),
        "annual_from": payload.get("annual_from"),
        "annual_to": payload.get("annual_to"),
        "due_time": payload.get("due_time") or "상시채용",
        "skill_tags": [str(t) for t in (payload.get("skill_tags") or []) if t],
        "pay": None,
        "link": None,
        "deadline": None,
        "collected_at": record.get("collected_at"),
    }


def normalize_work24(record: dict[str, Any]) -> dict[str, Any] | None:
    payload = record["payload"]
    source_id = str(payload.get("source_id") or record.get("source_id") or "")
    if not source_id:
        return None
    return {
        "source": "work24",
        "source_id": source_id,
        "company": clean_text(payload.get("company")),
        "position": clean_text(payload.get("title")),
        "location": clean_text(payload.get("location")),
        "intro": None,
        "main_tasks": clean_text(payload.get("description")),
        "requirements": clean_text(payload.get("requirements")),
        "preferred_points": clean_text(payload.get("preferred")),
        "benefits": None,
        "employment_type": None,
        "is_newbie": None,
        "annual_from": None,
        "annual_to": None,
        "due_time": payload.get("deadline") or "채용시까지",
        "skill_tags": [],
        "pay": clean_text(payload.get("pay")),
        "link": payload.get("link"),
        "deadline": payload.get("deadline"),
        "collected_at": record.get("collected_at"),
    }


NORMALIZERS = {
    "wanted": normalize_wanted,
    "work24": normalize_work24,
}


def build_full_text(row: dict[str, Any]) -> str:
    """임베딩 입력용 단일 문서 텍스트 합성."""
    parts: list[str] = []
    if row.get("company"):
        parts.append(f"[회사] {row['company']}")
    if row.get("position"):
        parts.append(f"[포지션] {row['position']}")
    if row.get("annual_from") is not None or row.get("annual_to") is not None:
        parts.append(f"[경력요건] {row.get('annual_from') or 0}년 ~ {row.get('annual_to') or 0}년")
    if row.get("is_newbie"):
        parts.append("[신입 가능]")
    if row.get("skill_tags"):
        parts.append(f"[기술스택] {', '.join(row['skill_tags'])}")
    if row.get("main_tasks"):
        parts.append(f"[주요업무] {row['main_tasks']}")
    if row.get("requirements"):
        parts.append(f"[자격요건] {row['requirements']}")
    if row.get("preferred_points"):
        parts.append(f"[우대사항] {row['preferred_points']}")
    if row.get("location"):
        parts.append(f"[위치] {row['location']}")
    return "\n".join(parts)


def build_silver_frame(raw_records: list[dict[str, Any]]) -> pl.DataFrame:
    """bronze 레코드를 통합 스키마로 정제·중복제거한 DataFrame을 만든다."""
    normalized: list[dict[str, Any]] = []
    for record in raw_records:
        normalizer = NORMALIZERS.get(record["source"])
        if normalizer is None:
            logger.warning("알 수 없는 소스: %s", record["source"])
            continue
        try:
            row = normalizer(record)
        except Exception as error:
            logger.warning("정제 실패 (%s/%s): %s", record["source"], record["source_id"], error)
            continue
        # 회사/포지션이 모두 없는 레코드는 쓸모 없다
        if row is not None and (row["company"] or row["position"]):
            normalized.append(row)

    if not normalized:
        return pl.DataFrame(schema=dict.fromkeys(COLUMNS, pl.String))

    frame = pl.DataFrame(normalized, schema=SCHEMA)
    frame = frame.unique(subset=["source", "source_id"], keep="last", maintain_order=True)
    return frame.with_columns(
        pl.struct(COLUMNS)
        .map_elements(build_full_text, return_dtype=pl.String)
        .alias("full_text")
    )


UPSERT_SQL = """
INSERT INTO silver.jobs (
    source, source_id, company, position, location, intro, main_tasks,
    requirements, preferred_points, benefits, employment_type, is_newbie,
    annual_from, annual_to, due_time, skill_tags, pay, link, deadline,
    full_text, collected_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
ON CONFLICT (source, source_id) DO UPDATE SET
    company = EXCLUDED.company,
    position = EXCLUDED.position,
    location = EXCLUDED.location,
    intro = EXCLUDED.intro,
    main_tasks = EXCLUDED.main_tasks,
    requirements = EXCLUDED.requirements,
    preferred_points = EXCLUDED.preferred_points,
    benefits = EXCLUDED.benefits,
    employment_type = EXCLUDED.employment_type,
    is_newbie = EXCLUDED.is_newbie,
    annual_from = EXCLUDED.annual_from,
    annual_to = EXCLUDED.annual_to,
    due_time = EXCLUDED.due_time,
    skill_tags = EXCLUDED.skill_tags,
    pay = EXCLUDED.pay,
    link = EXCLUDED.link,
    deadline = EXCLUDED.deadline,
    full_text = EXCLUDED.full_text,
    collected_at = EXCLUDED.collected_at,
    updated_at = now()
"""

INSERT_PARAMS = [
    "source", "source_id", "company", "position", "location",
    "intro", "main_tasks", "requirements", "preferred_points",
    "benefits", "employment_type", "is_newbie", "annual_from",
    "annual_to", "due_time", "skill_tags", "pay", "link",
    "deadline", "full_text", "collected_at",
]


async def run() -> int:
    raw_records = await fetch(
        "SELECT source, source_id, payload, collected_at FROM bronze.raw_postings"
    )
    if not raw_records:
        logger.warning("silver: bronze 데이터 없음")
        return 0

    frame = await asyncio.to_thread(build_silver_frame, [dict(r) for r in raw_records])
    if frame.is_empty():
        return 0

    rows = frame.to_dicts()
    await executemany(
        UPSERT_SQL,
        [tuple(row[col] for col in INSERT_PARAMS) for row in rows],
    )
    logger.info("silver upsert: %d건", len(rows))
    return len(rows)

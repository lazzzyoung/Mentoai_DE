import importlib.util
import json
from pathlib import Path
from typing import Generator

import pytest
from pyspark.sql import SparkSession


def _load_text_cleaner_module():
    module_path = (
        Path(__file__).resolve().parents[2] / "spark" / "utils" / "text_cleaner.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_text_cleaner_module", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("text_cleaner 모듈을 로드할 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def spark() -> Generator[SparkSession, None, None]:
    try:
        session = (
            SparkSession.builder.master("local[1]")
            .appName("test_text_cleaner")
            .getOrCreate()
        )
    except Exception as exc:
        pytest.skip(f"Java/Spark runtime unavailable: {exc}")

    yield session
    session.stop()


def test_clean_job_details_handles_wanted_and_recruit24_payloads(
    spark: SparkSession,
) -> None:
    module = _load_text_cleaner_module()
    wanted_payload = {
        "source": "wanted",
        "source_id": "12345",
        "collected_at": "2026-02-07T10:00:00Z",
        "raw_data": {
            "id": 12345,
            "status": "active",
            "is_newbie": True,
            "employment_type": "정규직",
            "annual_from": 2,
            "annual_to": 5,
            "due_time": "2026-03-31",
            "address": {"full_location": "서울 강남구"},
            "detail": {
                "position": "Data Engineer",
                "intro": "데이터 플랫폼 운영",
                "main_tasks": "배치/스트리밍 파이프라인 개발",
                "requirements": "Python, Spark",
                "preferred_points": "Kafka",
                "benefits": "원격 근무",
                "hire_rounds": "서류-면접",
            },
            "company": {"name": "Wanted Corp"},
            "skill_tags": ["Python", "Spark"],
        },
    }
    recruit24_payload = {
        "source": "recruit24",
        "source_id": "K165000001234",
        "company": "Recruit24 Corp",
        "title": "Backend Engineer",
        "location": "서울 송파구",
        "description": "API 서버 개발",
        "requirements": "FastAPI 경험",
        "preferred_qualifications": "Kafka 운영 경험",
        "deadline": "2026-04-01",
        "collected_at": "2026-02-07T11:00:00Z",
    }

    raw_df = spark.createDataFrame(
        [
            {"value": json.dumps(wanted_payload, ensure_ascii=False)},
            {"value": json.dumps(recruit24_payload, ensure_ascii=False)},
        ]
    )

    result = module.clean_job_details(raw_df).collect()
    rows_by_company = {row.company: row for row in result}

    assert len(result) == 2
    assert rows_by_company["Wanted Corp"].position == "Data Engineer"
    assert rows_by_company["Recruit24 Corp"].position == "Backend Engineer"
    assert rows_by_company["Recruit24 Corp"].main_tasks == "API 서버 개발"
    assert rows_by_company["Recruit24 Corp"].requirements == "FastAPI 경험"
    assert rows_by_company["Recruit24 Corp"].preferred_points == "Kafka 운영 경험"
    assert rows_by_company["Recruit24 Corp"].id is not None


def test_clean_job_details_does_not_merge_different_sources_with_same_numeric_id(
    spark: SparkSession,
) -> None:
    module = _load_text_cleaner_module()
    wanted_payload = {
        "source": "wanted",
        "source_id": "123",
        "collected_at": "2026-02-07T10:00:00Z",
        "raw_data": {
            "id": 123,
            "status": "active",
            "address": {"full_location": "서울"},
            "detail": {"position": "Data Engineer"},
            "company": {"name": "Wanted"},
        },
    }
    recruit24_payload = {
        "source": "recruit24",
        "source_id": "K123",
        "company": "Recruit24",
        "title": "Backend Engineer",
        "location": "서울",
        "description": "서비스 운영",
        "requirements": "Python",
        "preferred_qualifications": "Kafka",
        "deadline": "2026-04-01",
        "collected_at": "2026-02-07T11:00:00Z",
    }

    raw_df = spark.createDataFrame(
        [
            {"value": json.dumps(wanted_payload, ensure_ascii=False)},
            {"value": json.dumps(recruit24_payload, ensure_ascii=False)},
        ]
    )

    result = module.clean_job_details(raw_df).collect()

    assert len(result) == 2

from datetime import UTC, datetime

from mentoai.pipeline.silver import (
    build_full_text,
    build_silver_frame,
    clean_text,
    normalize_wanted,
    normalize_work24,
)

COLLECTED_AT = datetime(2026, 8, 1, tzinfo=UTC)


def make_wanted_record(source_id: int = 12345) -> dict:
    return {
        "source": "wanted",
        "source_id": str(source_id),
        "collected_at": COLLECTED_AT,
        "payload": {
            "id": source_id,
            "status": "ACTIVE",
            "is_newbie": False,
            "employment_type": "정규직",
            "annual_from": 3,
            "annual_to": 7,
            "due_time": None,
            "address": {"full_location": "서울 강남구"},
            "company": {"name": "테스트컴퍼니"},
            "skill_tags": ["Python", "Airflow", "dbt"],
            "detail": {
                "position": "데이터 엔지니어",
                "intro": "<p>소개  텍스트</p>",
                "main_tasks": "파이프라인 <b>구축</b> 및 운영",
                "requirements": "SQL, 클라우드 경험",
                "preferred_points": "Spark, Kafka",
                "benefits": "4대보험",
                "hire_rounds": "서류 → 면접",
            },
        },
    }


def make_work24_record(source_id: str = "K12345678901234") -> dict:
    return {
        "source": "work24",
        "source_id": source_id,
        "collected_at": COLLECTED_AT,
        "payload": {
            "source_id": source_id,
            "company": "공공기관",
            "title": "데이터 분석가",
            "link": "https://www.work.go.kr/example",
            "pay": "연봉 3,000만원",
            "location": "대전 유성구",
            "reg_date": "2026-08-01",
            "deadline": "2026-08-15",
            "description": "데이터 분석 및 대시보드 구축",
            "requirements": "경력조건: 2년 이상 | 학력: 대졸",
            "preferred": "우대조건: R, Python",
        },
    }


def test_clean_text_strips_html_and_whitespace() -> None:
    assert clean_text("<p>안녕   <b>하세요</b></p>") == "안녕 하세요"
    assert clean_text(None) is None
    assert clean_text("") is None
    assert clean_text("   ") is None


def test_normalize_wanted_flattens_nested_payload() -> None:
    row = normalize_wanted(make_wanted_record())
    assert row is not None
    assert row["source"] == "wanted"
    assert row["source_id"] == "12345"
    assert row["company"] == "테스트컴퍼니"
    assert row["position"] == "데이터 엔지니어"
    assert row["intro"] == "소개 텍스트"  # HTML 제거 확인
    assert row["main_tasks"] == "파이프라인 구축 및 운영"
    assert row["due_time"] == "상시채용"  # null 대체 기본값
    assert row["skill_tags"] == ["Python", "Airflow", "dbt"]
    assert row["annual_from"] == 3
    assert row["is_newbie"] is False


def test_normalize_wanted_drops_record_without_id() -> None:
    record = make_wanted_record()
    record["payload"]["id"] = None
    record["source_id"] = ""
    assert normalize_wanted(record) is None


def test_normalize_work24_maps_list_fields() -> None:
    row = normalize_work24(make_work24_record())
    assert row is not None
    assert row["source"] == "work24"
    assert row["position"] == "데이터 분석가"
    assert row["main_tasks"] == "데이터 분석 및 대시보드 구축"
    assert row["requirements"] == "경력조건: 2년 이상 | 학력: 대졸"
    assert row["preferred_points"] == "우대조건: R, Python"
    assert row["due_time"] == "2026-08-15"
    assert row["pay"] == "연봉 3,000만원"
    assert row["skill_tags"] == []


def test_build_full_text_contains_sections() -> None:
    row = normalize_wanted(make_wanted_record())
    assert row is not None
    text = build_full_text(row)
    assert "[회사] 테스트컴퍼니" in text
    assert "[포지션] 데이터 엔지니어" in text
    assert "[경력요건] 3년 ~ 7년" in text
    assert "[기술스택] Python, Airflow, dbt" in text
    assert "[주요업무]" in text
    assert "[신입 가능]" not in text


def test_build_silver_frame_dedups_keeping_latest() -> None:
    older = make_wanted_record(source_id=1)
    newer = make_wanted_record(source_id=1)
    newer["payload"]["company"] = {"name": "새로운컴퍼니"}
    work24 = make_work24_record()

    frame = build_silver_frame([older, newer, work24])

    assert frame.height == 2  # 중복 제거
    wanted_row = frame.filter(frame["source"] == "wanted").to_dicts()[0]
    assert wanted_row["company"] == "새로운컴퍼니"  # keep="last"
    assert frame["full_text"].is_not_null().all()
    assert (frame["full_text"].str.len_chars() > 0).all()


def test_build_silver_frame_skips_junk_rows() -> None:
    junk = make_wanted_record()
    junk["payload"]["company"] = {"name": ""}
    junk["payload"]["detail"]["position"] = None
    frame = build_silver_frame([junk])
    assert frame.is_empty()

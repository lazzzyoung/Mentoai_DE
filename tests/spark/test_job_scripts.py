import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_module(module_name: str, module_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{module_path} 모듈을 로드할 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        pytest.skip(f"Optional dependency unavailable for {module_name}: {exc}")
    return module


def test_jdbc_properties_contains_required_postgres_keys() -> None:
    module_path = (
        Path(__file__).resolve().parents[2] / "spark" / "job_process_silver.py"
    )
    module = _load_module("test_job_process_silver", module_path)
    props = module._jdbc_properties("airflow", "secret")

    assert props == {
        "user": "airflow",
        "password": "secret",
        "driver": "org.postgresql.Driver",
    }


def test_build_context_text_formats_job_payload() -> None:
    module_path = Path(__file__).resolve().parents[2] / "spark" / "job_upsert_gold.py"
    module = _load_module("test_job_upsert_gold", module_path)
    row = SimpleNamespace(
        company="MentoAI",
        position="Data Engineer",
        annual_from=1,
        annual_to=3,
        skill_tags=["Python", "Spark"],
        main_tasks="배치 파이프라인 개발",
        requirements="SQL, Airflow",
        preferred_points="Kafka",
    )

    context = module._build_context_text(row)

    assert "[회사] MentoAI" in context
    assert "[포지션] Data Engineer" in context
    assert "[기술스택] Python, Spark" in context
    assert "[주요업무] 배치 파이프라인 개발" in context


def test_build_context_text_uses_none_when_skill_tags_empty() -> None:
    module_path = Path(__file__).resolve().parents[2] / "spark" / "job_upsert_gold.py"
    module = _load_module("test_job_upsert_gold_empty", module_path)
    row = SimpleNamespace(
        company="MentoAI",
        position="Backend Engineer",
        annual_from=0,
        annual_to=2,
        skill_tags=[],
        main_tasks="API 개발",
        requirements="FastAPI",
        preferred_points="Redis",
    )

    context = module._build_context_text(row)

    assert "[기술스택] 없음" in context

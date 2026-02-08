import importlib.util
from pathlib import Path


def _load_recruit24_parser_module():
    module_path = (
        Path(__file__).resolve().parents[2] / "kafka" / "utils" / "recruit24_parser.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_recruit24_parser_module", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("recruit24_parser 모듈을 로드할 수 없습니다.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_auth_no_extracts_worknet_auth_number() -> None:
    module = _load_recruit24_parser_module()
    html = '<a href="/empInfo/?wantedAuthNo=K165000001234">입사지원</a>'

    auth_no = module.parse_auth_no(html)

    assert auth_no == "K165000001234"


def test_build_job_message_sets_source_and_required_fields() -> None:
    module = _load_recruit24_parser_module()
    parsed_row = {
        "auth_no": "K165000001234",
        "company": "MentoAI",
        "title": "백엔드 개발자",
        "pay": "연봉 5000만원",
        "location": "서울 강남구",
        "reg_date": "2026-02-07",
        "deadline": "2026-03-01",
    }
    detail = {
        "job_description": "FastAPI 기반 서비스 개발",
        "requirements": "Python 3년 이상",
        "preferred": "Spark 경험",
    }

    message = module.build_job_message(parsed_row, detail)

    assert message["source"] == "recruit24"
    assert message["source_id"] == parsed_row["auth_no"]
    assert message["company"] == parsed_row["company"]
    assert message["title"] == parsed_row["title"]
    assert message["requirements"] == detail["requirements"]
    assert message["preferred_qualifications"] == detail["preferred"]

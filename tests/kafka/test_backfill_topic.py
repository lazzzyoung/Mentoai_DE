import importlib.util
import sys
from pathlib import Path


def _load_backfill_module():
    root_dir = Path(__file__).resolve().parents[2]
    kafka_dir = root_dir / "kafka"
    module_path = kafka_dir / "producer_recruit24_backfill.py"

    sys.path.insert(0, str(kafka_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "test_producer_recruit24_backfill_module",
            module_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("producer_recruit24_backfill 모듈을 로드할 수 없습니다.")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(kafka_dir))


def test_resolve_topic_name_prefers_backfill_topic(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BACKFILL_TOPIC", "career_backfill_custom")
    monkeypatch.setenv("KAFKA_TOPIC_NAME", "career_raw")

    module = _load_backfill_module()

    assert module.resolve_topic_name() == "career_backfill_custom"


def test_resolve_topic_name_falls_back_to_kafka_topic(monkeypatch) -> None:
    monkeypatch.delenv("KAFKA_BACKFILL_TOPIC", raising=False)
    monkeypatch.setenv("KAFKA_TOPIC_NAME", "career_raw")

    module = _load_backfill_module()

    assert module.resolve_topic_name() == "career_raw"

from mentoai.ai.embeddings import embed_prefixes
from mentoai.ai.scoring import build_reason, similarity_to_score, skill_overlap


def test_similarity_to_score_clamps_bounds() -> None:
    assert similarity_to_score(0.87) == 87
    assert similarity_to_score(1.5) == 99  # 상한 클램프
    assert similarity_to_score(0.12) == 40  # 하한 클램프


def test_skill_overlap_case_insensitive() -> None:
    overlap = skill_overlap(
        ["Python", "sql", "Airflow"], ["python", "Spark", "SQL", "Kafka"]
    )
    assert overlap == ["Python", "sql"]


def test_skill_overlap_empty_tags() -> None:
    assert skill_overlap(["Python"], []) == []


def test_build_reason_with_overlap_and_career_gap() -> None:
    job = {
        "skill_tags": ["Python", "Spark", "Kafka"],
        "annual_from": 4,
        "is_newbie": False,
    }
    reason = build_reason(["Python", "Kafka"], 2, job)
    assert "Python, Kafka" in reason
    assert "경력 요건(4년+)까지 2년 부족" in reason


def test_build_reason_newbie_friendly() -> None:
    job = {"skill_tags": [], "annual_from": 0, "is_newbie": True}
    reason = build_reason(["Python"], 0, job)
    assert "희망 직무와 공고 문맥이 유사" in reason
    assert "신입 지원 가능" in reason


def test_embed_prefixes_by_model_family() -> None:
    assert embed_prefixes("BAAI/bge-m3") == ("", "")
    assert embed_prefixes("intfloat/multilingual-e5-large") == ("query: ", "passage: ")

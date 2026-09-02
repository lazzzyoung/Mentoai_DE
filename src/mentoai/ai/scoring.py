"""추천 점수/사유 휴리스틱 - LLM 없이 즉시 응답하기 위한 순수 함수들."""


def similarity_to_score(similarity: float) -> int:
    """cosine similarity(0~1)를 40~99 점수로 변환."""
    return max(40, min(99, round(similarity * 100)))


def skill_overlap(user_skills: list[str], job_tags: list[str]) -> list[str]:
    tags = {tag.strip().lower() for tag in job_tags if tag}
    return [skill for skill in user_skills if skill.strip().lower() in tags]


def build_reason(user_skills: list[str], career_years: int, job: dict) -> str:
    overlap = skill_overlap(user_skills, job.get("skill_tags") or [])
    parts: list[str] = []
    if overlap:
        parts.append(f"보유 스킬({', '.join(overlap[:5])})이 포지션 기술스택과 일치")
    else:
        parts.append("희망 직무와 공고 문맥이 유사")

    annual_from = job.get("annual_from")
    if isinstance(annual_from, int) and annual_from > 0 and career_years < annual_from:
        parts.append(f"경력 요건({annual_from}년+)까지 {annual_from - career_years}년 부족")
    elif job.get("is_newbie"):
        parts.append("신입 지원 가능")
    return ", ".join(parts) + "."

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from server.app.core.config import CANDIDATE_LIMIT, RANK_RETRIEVAL_WEIGHT, RETRIEVAL_ALPHA
from server.app.repositories import job_repository
from server.app.services.embedding_service import embed_text

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣_+#.-]+")
CAREER_RANGE_PATTERN = re.compile(r"(\d{1,2})\s*[-~]\s*(\d{1,2})\s*년")
CAREER_MIN_PATTERN = re.compile(r"(\d{1,2})\s*년\s*이상")
CAREER_PLUS_PATTERN = re.compile(r"(\d{1,2})\s*\+\s*년")
CAREER_MAX_PATTERN = re.compile(r"(\d{1,2})\s*년\s*이하")
SKILL_SPLIT_PATTERN = re.compile(r"[,/|;]+")
ROLE_TEXT_SPLIT_PATTERN = re.compile(r"[-_/]+")
ROLE_FILTER_MIN_SCORE = 0.35

ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "backend": (
        "backend",
        "back end",
        "백엔드",
        "서버 개발",
        "서버개발",
        "server developer",
        "server engineer",
        "api engineer",
        "application engineer",
        "platform engineer",
        "java engineer",
        "spring engineer",
        "백엔드 엔지니어",
        "서버 엔지니어",
        "플랫폼 엔지니어",
    ),
    "frontend": (
        "frontend",
        "front end",
        "front",
        "프론트",
        "프런트",
        "프론트엔드",
        "프런트엔드",
        "웹 프론트",
        "프론트 개발",
        "프런트 개발",
        "ui engineer",
        "client engineer",
        "프론트엔드 엔지니어",
        "프런트엔드 엔지니어",
        "클라이언트 개발",
    ),
    "data": (
        "data engineer",
        "data engineering",
        "data platform engineer",
        "data pipeline engineer",
        "data warehouse engineer",
        "big data engineer",
        "bi engineer",
        "데이터 엔지니어",
        "데이터 엔지니어링",
        "데이터 플랫폼 엔지니어",
        "데이터 파이프라인 엔지니어",
        "데이터 웨어하우스 엔지니어",
        "데이터 플랫폼",
        "데이터 분석가",
        "데이터 파이프라인",
        "데이터 레이크",
        "data analytics engineer",
        "data analyst",
        "analytics engineer",
        "analytics",
        "etl",
        "data platform",
    ),
    "ai": (
        "ai engineer",
        "ml engineer",
        "machine learning engineer",
        "llm engineer",
        "ai research engineer",
        "machine learning",
        "인공지능",
        "머신러닝",
        "딥러닝",
        "ai 개발자",
    ),
    "devops": (
        "devops",
        "dev ops",
        "sre",
        "site reliability engineer",
        "platform ops",
        "infra engineer",
        "infrastructure engineer",
        "클라우드 엔지니어",
        "데브옵스",
        "인프라 엔지니어",
    ),
    "mobile": (
        "ios engineer",
        "android engineer",
        "mobile engineer",
        "react native",
        "flutter",
        "모바일 개발자",
        "앱 개발자",
    ),
    "qa": (
        "qa engineer",
        "test engineer",
        "quality assurance",
        "테스트 엔지니어",
        "품질 엔지니어",
    ),
    "security": (
        "security engineer",
        "application security",
        "cloud security",
        "정보보안",
        "보안 엔지니어",
    ),
    "design": (
        "designer",
        "디자이너",
        "ux",
        "ui",
        "product designer",
    ),
    "pm": (
        "product manager",
        "project manager",
        "product owner",
        "서비스 기획",
        "기획자",
        "pm",
        "po",
    ),
    "marketing": (
        "marketer",
        "marketing",
        "마케터",
        "브랜드 마케팅",
        "그로스 마케팅",
        "퍼포먼스 마케팅",
    ),
}
ROLE_RELATED_FAMILIES: dict[str, tuple[str, ...]] = {
    "backend": ("data", "ai"),
    "data": ("backend", "ai"),
    "ai": ("data", "backend"),
    "devops": ("backend", "data", "security"),
    "security": ("devops", "backend"),
    "mobile": ("frontend", "backend"),
    "qa": ("backend", "frontend", "mobile"),
    "frontend": ("design",),
    "design": ("frontend", "pm"),
    "pm": ("design", "marketing"),
    "marketing": ("pm",),
}


@dataclass(slots=True)
class RankedJob:
    job_id: int
    company: str
    title: str
    content: str
    score: float
    reason: str


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text or "") if token]


def _normalize_role_text(text: str) -> str:
    lowered = (text or "").lower()
    lowered = ROLE_TEXT_SPLIT_PATTERN.sub(" ", lowered)
    return " ".join(lowered.split())


def _contains_alias(normalized_text: str, normalized_tokens: set[str], alias: str) -> bool:
    target = _normalize_role_text(alias)
    if not target:
        return False
    if " " not in target:
        return target in normalized_tokens
    return target in normalized_text


def _extract_role_categories(text: str) -> set[str]:
    normalized_text = _normalize_role_text(text)
    if not normalized_text:
        return set()

    tokens = set(_tokenize(normalized_text))
    roles: set[str] = set()
    for role, aliases in ROLE_ALIASES.items():
        if any(_contains_alias(normalized_text, tokens, alias) for alias in aliases):
            roles.add(role)
    return roles


def _canonicalize_desired_role(desired_job: str) -> str | None:
    roles = _extract_role_categories(desired_job)
    if not roles:
        return None

    for preferred in (
        "backend",
        "frontend",
        "data",
        "ai",
        "devops",
        "mobile",
        "qa",
        "security",
        "pm",
        "design",
        "marketing",
    ):
        if preferred in roles:
            return preferred
    return next(iter(roles))


def _token_overlap_ratio(query_tokens: list[str], target_tokens: list[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0

    target_set = set(target_tokens)
    matched = sum(1 for token in query_tokens if token in target_set)
    return matched / len(query_tokens)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(v * v for v in left))
    right_norm = math.sqrt(sum(v * v for v in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _normalize_bm25(candidates: list[job_repository.JobCandidate]) -> dict[int, float]:
    if not candidates:
        return {}

    bm25_values = [candidate.bm25_score for candidate in candidates]
    min_score = min(bm25_values)
    max_score = max(bm25_values)

    if min_score == max_score:
        return {candidate.job_id: 1.0 for candidate in candidates}

    normalized: dict[int, float] = {}
    for candidate in candidates:
        normalized[candidate.job_id] = 1 - (
            (candidate.bm25_score - min_score) / (max_score - min_score)
        )
    return normalized


def _profile_weights_for_career(career_years: int) -> tuple[float, float, float]:
    if career_years <= 2:
        return (0.35, 0.50, 0.15)
    if career_years <= 6:
        return (0.35, 0.40, 0.25)
    return (0.30, 0.30, 0.40)


def _extract_required_career_bounds(text: str) -> tuple[int | None, int | None]:
    source = (text or "").lower()
    min_year: int | None = None
    max_year: int | None = None

    for start_text, end_text in CAREER_RANGE_PATTERN.findall(source):
        start = int(start_text)
        end = int(end_text)
        low, high = (start, end) if start <= end else (end, start)
        min_year = low if min_year is None else max(min_year, low)
        max_year = high if max_year is None else min(max_year, high)

    min_candidates = [
        int(value)
        for value in CAREER_MIN_PATTERN.findall(source) + CAREER_PLUS_PATTERN.findall(source)
    ]
    if min_candidates:
        parsed_min = max(min_candidates)
        min_year = parsed_min if min_year is None else max(min_year, parsed_min)

    max_candidates = [int(value) for value in CAREER_MAX_PATTERN.findall(source)]
    if max_candidates:
        parsed_max = min(max_candidates)
        max_year = parsed_max if max_year is None else min(max_year, parsed_max)

    if min_year is None and "시니어" in source:
        min_year = 7
    if min_year is None and max_year is None and "신입" in source:
        min_year, max_year = 0, 1
    if min_year is None and max_year is None and "주니어" in source:
        min_year, max_year = 0, 3

    if min_year is not None and max_year is not None and max_year < min_year:
        max_year = None

    return min_year, max_year


def _role_match_score(desired_job: str, candidate: job_repository.JobCandidate) -> float:
    desired = _normalize_role_text(desired_job)
    if not desired:
        return 0.5

    desired_role = _canonicalize_desired_role(desired)
    candidate_roles = _extract_role_categories(candidate.title)
    if desired_role:
        if desired_role in candidate_roles:
            return 1.0
        related_roles = set(ROLE_RELATED_FAMILIES.get(desired_role, ()))
        if related_roles and related_roles.intersection(candidate_roles):
            return 0.6
        if candidate_roles:
            return 0.05

    title = _normalize_role_text(candidate.title)
    content = _normalize_role_text(candidate.content[:500])
    if desired in title:
        return 1.0

    desired_tokens = _tokenize(desired)
    title_tokens = _tokenize(title)
    content_tokens = _tokenize(f"{title} {content}")

    title_overlap = _token_overlap_ratio(desired_tokens, title_tokens)
    content_overlap = _token_overlap_ratio(desired_tokens, content_tokens)
    return _clamp01(max(title_overlap, content_overlap * 0.6))


def _normalize_user_skill_tokens(user_skills: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in user_skills:
        if not raw:
            continue
        for chunk in SKILL_SPLIT_PATTERN.split(str(raw)):
            token = " ".join(chunk.strip().lower().split())
            token = token.strip("()[]{}")
            if not token or token == "없음":
                continue

            compact = re.sub(r"[^a-z0-9가-힣+#.]", "", token)
            if len(compact) < 2 and compact not in {"c", "r", "go"}:
                continue

            if token in seen:
                continue
            seen.add(token)
            normalized.append(token)
    return normalized


def _skill_in_text(skill: str, target_text: str, target_tokens: set[str], target_compact: str) -> bool:
    normalized = " ".join(skill.lower().split())
    if not normalized:
        return False

    if len(normalized) <= 2 and normalized.isalpha():
        return normalized in target_tokens

    compact = normalized.replace(" ", "").replace("-", "").replace(".", "")
    if normalized in target_text:
        return True
    if normalized in target_tokens:
        return True
    return bool(compact and compact in target_compact)


def _skills_match_score(user_skills: list[str], candidate: job_repository.JobCandidate) -> float:
    normalized_skills = _normalize_user_skill_tokens(user_skills)
    if not normalized_skills:
        return 0.5

    target_text = _normalize_role_text(f"{candidate.skills_text} {candidate.content}")
    target_tokens = set(_tokenize(target_text))
    target_compact = target_text.replace(" ", "").replace("-", "").replace(".", "")

    matched = sum(
        1
        for skill in normalized_skills
        if _skill_in_text(skill, target_text, target_tokens, target_compact)
    )
    return _clamp01(matched / len(normalized_skills))


def _career_match_score(user_career_years: int, candidate: job_repository.JobCandidate) -> float:
    min_year, max_year = _extract_required_career_bounds(candidate.content)
    if min_year is None and max_year is None:
        return 0.5

    years = max(0, int(user_career_years))

    if min_year is not None and years < min_year:
        return _clamp01(years / max(min_year, 1))

    if max_year is not None and years > max_year:
        gap = years - max_year
        soft_penalty = 1 - (gap / max(years, 1))
        return max(0.6, _clamp01(soft_penalty))

    return 1.0


def _compute_profile_score(
    candidate: job_repository.JobCandidate,
    *,
    desired_job: str,
    career_years: int,
    skills: list[str],
) -> tuple[float, float, float, float]:
    role_score = _role_match_score(desired_job, candidate)
    skills_score = _skills_match_score(skills, candidate)
    career_score = _career_match_score(career_years, candidate)
    w_role, w_skills, w_career = _profile_weights_for_career(career_years)

    profile_score = (w_role * role_score) + (w_skills * skills_score) + (w_career * career_score)
    return role_score, skills_score, career_score, _clamp01(profile_score)


def _blend_final_score(retrieval_score: float, profile_score: float) -> float:
    retrieval_weight = _clamp01(RANK_RETRIEVAL_WEIGHT)
    return _clamp01((retrieval_weight * retrieval_score) + ((1 - retrieval_weight) * profile_score))


def _build_reason(
    candidate: job_repository.JobCandidate,
    semantic_score: float,
    role_score: float | None = None,
    skills_score: float | None = None,
    career_score: float | None = None,
) -> str:
    if role_score is not None and role_score < 0.25:
        return "희망 직무와 공고 직무가 달라 적합도가 낮습니다."

    if semantic_score >= 0.7 and (
        role_score is None or skills_score is None or career_score is None
    ):
        return "경험과 기술 맥락이 공고 요구사항과 잘 맞습니다."

    if role_score is not None and skills_score is not None and career_score is not None:
        weakest_key, weakest_value = min(
            (
                ("role", role_score),
                ("skills", skills_score),
                ("career", career_score),
            ),
            key=lambda item: item[1],
        )
        if weakest_value >= 0.6:
            return "경험과 기술 맥락이 공고 요구사항과 잘 맞습니다."
        if weakest_key == "career":
            return "직무는 유사하지만 요구 경력과의 간격이 있어 보완이 필요합니다."
        if weakest_key == "skills" and candidate.skills_text:
            return f"기술 스택 키워드가 일부 일치합니다: {candidate.skills_text[:40]}"
        return "희망 직무와 공고 핵심 내용이 유사합니다."

    if candidate.skills_text:
        return f"기술 스택 키워드가 일부 일치합니다: {candidate.skills_text[:40]}"
    return "희망 직무와 공고 핵심 내용이 유사합니다."


async def retrieve_jobs(
    query_text: str,
    *,
    desired_job: str,
    career_years: int,
    skills: list[str],
    limit: int,
) -> list[RankedJob]:
    candidates = await job_repository.search_jobs_fts(query_text, CANDIDATE_LIMIT)
    if not candidates:
        return []

    query_vector = await embed_text(query_text)
    embeddings = await job_repository.fetch_embeddings(
        [candidate.job_id for candidate in candidates]
    )

    bm25_scores = _normalize_bm25(candidates)
    ranked: list[RankedJob] = []
    role_filtered_ranked: list[RankedJob] = []
    desired_role = _canonicalize_desired_role(desired_job)

    for candidate in candidates:
        semantic = _cosine_similarity(query_vector, embeddings.get(candidate.job_id, []))
        semantic_norm = (semantic + 1) / 2
        lexical_norm = bm25_scores.get(candidate.job_id, 0.0)
        retrieval_score = (RETRIEVAL_ALPHA * lexical_norm) + ((1 - RETRIEVAL_ALPHA) * semantic_norm)

        role_score, skills_score, career_score, profile_score = _compute_profile_score(
            candidate,
            desired_job=desired_job,
            career_years=career_years,
            skills=skills,
        )
        final_score = _blend_final_score(retrieval_score, profile_score)

        ranked_job = RankedJob(
            job_id=candidate.job_id,
            company=candidate.company,
            title=candidate.title,
            content=candidate.content,
            score=final_score,
            reason=_build_reason(
                candidate,
                semantic_norm,
                role_score=role_score,
                skills_score=skills_score,
                career_score=career_score,
            ),
        )
        ranked.append(ranked_job)
        if desired_role is None or role_score >= ROLE_FILTER_MIN_SCORE:
            role_filtered_ranked.append(ranked_job)

    result_pool = role_filtered_ranked if role_filtered_ranked else ranked
    result_pool.sort(key=lambda item: item.score, reverse=True)
    return result_pool[:limit]

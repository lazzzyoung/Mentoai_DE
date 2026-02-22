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
    desired = (desired_job or "").strip().lower()
    if not desired:
        return 0.5

    title = (candidate.title or "").lower()
    content = (candidate.content or "").lower()

    if desired in title:
        return 1.0
    if desired in content:
        return 0.9

    desired_tokens = _tokenize(desired)
    title_tokens = _tokenize(title)
    content_tokens = _tokenize(f"{title} {content}")

    title_overlap = _token_overlap_ratio(desired_tokens, title_tokens)
    content_overlap = _token_overlap_ratio(desired_tokens, content_tokens)
    return _clamp01(max(title_overlap, content_overlap * 0.9))


def _skills_match_score(user_skills: list[str], candidate: job_repository.JobCandidate) -> float:
    normalized_skills = [skill.strip().lower() for skill in user_skills if skill and skill.strip()]
    if not normalized_skills:
        return 0.5

    target_text = f"{candidate.skills_text} {candidate.content}".lower()
    matched = sum(1 for skill in normalized_skills if skill in target_text)
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

        ranked.append(
            RankedJob(
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
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]

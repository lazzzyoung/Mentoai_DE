from __future__ import annotations

import math
from dataclasses import dataclass

from server.app.core.config import CANDIDATE_LIMIT, RETRIEVAL_ALPHA
from server.app.repositories import job_repository
from server.app.services.embedding_service import embed_text


@dataclass(slots=True)
class RankedJob:
    job_id: int
    company: str
    title: str
    content: str
    score: float
    reason: str


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


def _build_reason(candidate: job_repository.JobCandidate, semantic_score: float) -> str:
    if semantic_score >= 0.85:
        return "요구 기술·경험과의 일치도가 높은 편입니다."
    if semantic_score >= 0.65:
        return "요구사항과의 일치도가 보통 수준입니다. 핵심 경험 보완이 필요합니다."
    if candidate.skills_text:
        return f"기술 스택 키워드가 일부 일치합니다: {candidate.skills_text[:40]}"
    return "직무 키워드는 유사하지만 실무 경험 근거가 부족할 수 있습니다."


async def retrieve_jobs(query_text: str, limit: int) -> list[RankedJob]:
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
        final_score = RETRIEVAL_ALPHA * lexical_norm + (1 - RETRIEVAL_ALPHA) * semantic_norm

        ranked.append(
            RankedJob(
                job_id=candidate.job_id,
                company=candidate.company,
                title=candidate.title,
                content=candidate.content,
                score=final_score,
                reason=_build_reason(candidate, semantic_norm),
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]

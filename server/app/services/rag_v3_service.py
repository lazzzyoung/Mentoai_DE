from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from fastapi import HTTPException

from server.app.core.config import (
    ANALYSIS_CACHE_MAX_ENTRIES,
    ANALYSIS_CACHE_SWEEP_SECONDS,
    ANALYSIS_CACHE_TTL_SECONDS,
    ANALYSIS_MODEL,
    CANDIDATE_LIMIT,
    OPENAI_API_KEY,
    RECOMMENDATION_LIMIT,
)
from server.app.prompts import JOB_ANALYSIS_PROMPT_TEMPLATE
from server.app.repositories import job_repository
from server.app.repositories.user_repository import create_quick_user, fetch_user_info
from server.app.schemas.v3 import (
    ActionItem,
    DetailedAnalysisResponse,
    JobSummary,
    QuickLoginRequest,
    QuickLoginResponse,
    RecommendationListResponse,
    UserProfileSummary,
)
from server.app.services.hybrid_retriever import retrieve_jobs

logger = logging.getLogger(__name__)

_llm: Any | None = None
_llm_lock = asyncio.Lock()
MIN_RECOMMENDATION_POOL = 20
MAX_RECOMMENDATION_LIMIT = 200


@dataclass(slots=True)
class AnalysisCacheEntry:
    expires_at: float
    payload: dict[str, Any]


_analysis_cache: OrderedDict[str, AnalysisCacheEntry] = OrderedDict()
_analysis_cache_lock = asyncio.Lock()
_analysis_inflight: dict[str, asyncio.Task[dict[str, Any]]] = {}
_analysis_inflight_lock = asyncio.Lock()
_last_cache_sweep_at = 0.0


def _to_user_profile(user_info: dict[str, Any]) -> UserProfileSummary:
    desired_job = str(user_info.get("desired_job") or "미입력")

    raw_career_years = user_info.get("career_years")
    try:
        career_years = int(raw_career_years) if raw_career_years is not None else 0
    except (TypeError, ValueError):
        career_years = 0

    raw_skills = user_info.get("skills") or []
    skills = [str(skill).strip() for skill in raw_skills if str(skill).strip()]

    return UserProfileSummary(
        desired_job=desired_job,
        career_years=career_years,
        skills=skills,
    )


def _build_user_query_text(user_profile: UserProfileSummary) -> str:
    skills_text = ", ".join(user_profile.skills) if user_profile.skills else "없음"
    return (
        f"희망직무: {user_profile.desired_job}, "
        f"보유기술: {skills_text}, "
        f"경력: {user_profile.career_years}년"
    )


def _to_match_score(score: float) -> int:
    bounded = max(0.0, min(score, 1.0))
    if bounded <= 0.5:
        mapped = (bounded / 0.5) * 70
    else:
        mapped = 70 + (((bounded - 0.5) / 0.5) * 30)
    return int(round(mapped))


def _to_recommendations(ranked_jobs: list[Any]) -> list[JobSummary]:
    return [
        JobSummary(
            job_id=job.job_id,
            company=job.company,
            title=job.title,
            match_score=_to_match_score(job.score),
            max_score=100,
            reason=job.reason,
        )
        for job in ranked_jobs
    ]


def _clamp_limit(value: int, *, lower: int = 1, upper: int = MAX_RECOMMENDATION_LIMIT) -> int:
    return max(lower, min(upper, int(value)))


def _resolve_recommendation_limit(requested_limit: int | None = None) -> int:
    """추천 개수를 요청값/기본값으로 정하고 안전한 범위로 제한한다."""
    if requested_limit is None:
        desired = max(RECOMMENDATION_LIMIT, MIN_RECOMMENDATION_POOL)
    else:
        desired = requested_limit

    upper_bound = min(CANDIDATE_LIMIT, MAX_RECOMMENDATION_LIMIT)
    return _clamp_limit(desired, lower=1, upper=max(1, upper_bound))


async def quick_login(data: QuickLoginRequest) -> QuickLoginResponse:
    try:
        user_id = await create_quick_user(
            user_name=data.user_name,
            desired_job=data.desired_job,
            career_years=data.career_years,
            skills=data.skills,
        )
        user_info = await fetch_user_info(user_id)

        user_name = str(user_info.get("username") or data.user_name)
        return QuickLoginResponse(
            user_id=user_id,
            user_name=user_name,
            user_profile=_to_user_profile(user_info),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Quick login error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="로그인 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def recommend_jobs_list(user_id: int, limit: int | None = None) -> RecommendationListResponse:
    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        query_text = _build_user_query_text(user_profile)

        ranked_jobs = await retrieve_jobs(
            query_text,
            desired_job=user_profile.desired_job,
            career_years=user_profile.career_years,
            skills=user_profile.skills,
            limit=_resolve_recommendation_limit(limit),
        )
        recommendations = _to_recommendations(ranked_jobs)

        return RecommendationListResponse(
            user_id=user_id,
            user_name=str(user_info.get("username") or "사용자"),
            user_profile=user_profile,
            recommendations=recommendations,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Recommend jobs error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="추천 결과를 준비하는 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def _get_llm() -> Any | None:
    global _llm

    if _llm is not None:
        return _llm
    if not OPENAI_API_KEY:
        return None

    async with _llm_lock:
        if _llm is not None:
            return _llm

        try:
            from langchain_openai import ChatOpenAI

            chat_openai = cast(Any, ChatOpenAI)
            _llm = chat_openai(
                model=ANALYSIS_MODEL,
                api_key=OPENAI_API_KEY,
                temperature=0.3,
                max_retries=2,
            )
        except Exception as error:  # pragma: no cover - optional path
            logger.warning("LLM init failed, using fallback analysis: %s", error)
            _llm = None

    return _llm


def _fallback_analysis(title: str, company: str) -> DetailedAnalysisResponse:
    return DetailedAnalysisResponse(
        job_title=title,
        company_name=company,
        current_score=70,
        max_score=100,
        analysis_summary="핵심 역량은 일부 맞지만 실무 프로젝트 경험 보강이 필요합니다.",
        required_tech_stack=["Python", "SQL", "데이터 파이프라인"],
        action_plan=[
            ActionItem(
                category="프로젝트",
                item_name="미니 ETL 프로젝트",
                description="공고 데이터를 수집해 정제 후 데이터베이스에 저장하는 포트폴리오를 완성하세요.",
                expected_score_up=8,
            )
        ],
        interview_tip="최근 프로젝트에서 맡은 역할과 문제 해결 과정을 수치와 함께 설명하세요.",
    )


async def _run_llm_analysis(
    llm: Any,
    query_text: str,
    job: dict[str, Any],
) -> dict[str, Any]:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    parser = JsonOutputParser(pydantic_object=DetailedAnalysisResponse)
    prompt = ChatPromptTemplate.from_template(JOB_ANALYSIS_PROMPT_TEMPLATE)

    chain = prompt | llm | parser
    result = await chain.ainvoke(
        {
            "user_specs": query_text,
            "company": job["company"],
            "title": job["title"],
            "content": job["full_text"],
            "format_instructions": parser.get_format_instructions(),
        }
    )
    return result if isinstance(result, dict) else {}


def _finalize_analysis(result: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    if not result:
        result = _fallback_analysis(job["title"], job["company"]).model_dump()

    result["job_title"] = job["title"]
    result["company_name"] = job["company"]
    return result


def _build_analysis_cache_key(
    *,
    user_id: int,
    job_id: int,
    user_profile: UserProfileSummary,
    job: dict[str, Any],
) -> str:
    normalized_skills = ",".join(
        sorted(skill.strip().lower() for skill in user_profile.skills if skill and skill.strip())
    )
    payload = "|".join(
        [
            str(user_id),
            str(job_id),
            user_profile.desired_job.strip().lower(),
            str(user_profile.career_years),
            normalized_skills,
            str(job.get("company") or ""),
            str(job.get("title") or ""),
            str(job.get("full_text") or ""),
            ANALYSIS_MODEL,
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


async def _get_cached_analysis(key: str) -> dict[str, Any] | None:
    global _last_cache_sweep_at

    now = time.monotonic()
    sweep_interval = max(1, ANALYSIS_CACHE_SWEEP_SECONDS)
    async with _analysis_cache_lock:
        if now - _last_cache_sweep_at >= sweep_interval:
            expired_keys = [
                cache_key
                for cache_key, entry in _analysis_cache.items()
                if entry.expires_at <= now
            ]
            for expired_key in expired_keys:
                _analysis_cache.pop(expired_key, None)
            _last_cache_sweep_at = now

        entry = _analysis_cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            _analysis_cache.pop(key, None)
            return None

        _analysis_cache.move_to_end(key)
        return deepcopy(entry.payload)


async def _set_cached_analysis(key: str, payload: dict[str, Any]) -> None:
    global _last_cache_sweep_at

    ttl_seconds = max(1, ANALYSIS_CACHE_TTL_SECONDS)
    max_entries = max(1, ANALYSIS_CACHE_MAX_ENTRIES)
    now = time.monotonic()
    expires_at = now + ttl_seconds
    sweep_interval = max(1, ANALYSIS_CACHE_SWEEP_SECONDS)

    async with _analysis_cache_lock:
        if now - _last_cache_sweep_at >= sweep_interval:
            expired_keys = [
                cache_key
                for cache_key, entry in _analysis_cache.items()
                if entry.expires_at <= now
            ]
            for expired_key in expired_keys:
                _analysis_cache.pop(expired_key, None)
            _last_cache_sweep_at = now

        _analysis_cache[key] = AnalysisCacheEntry(
            expires_at=expires_at,
            payload=deepcopy(payload),
        )
        _analysis_cache.move_to_end(key)
        while len(_analysis_cache) > max_entries:
            _analysis_cache.popitem(last=False)


async def _run_cached_analysis(
    *,
    cache_key: str,
    llm: Any,
    query_text: str,
    job: dict[str, Any],
) -> dict[str, Any]:
    cached = await _get_cached_analysis(cache_key)
    if cached is not None:
        return cached

    async with _analysis_inflight_lock:
        inflight_task = _analysis_inflight.get(cache_key)
        if inflight_task is None:
            inflight_task = asyncio.create_task(_run_llm_analysis(llm, query_text, job))
            _analysis_inflight[cache_key] = inflight_task

    try:
        analysis = await inflight_task
    finally:
        async with _analysis_inflight_lock:
            if _analysis_inflight.get(cache_key) is inflight_task:
                _analysis_inflight.pop(cache_key, None)

    finalized = _finalize_analysis(analysis, job)
    await _set_cached_analysis(cache_key, finalized)
    return deepcopy(finalized)


async def analyze_job_detail(job_id: int, user_id: int) -> dict[str, Any]:
    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        query_text = _build_user_query_text(user_profile)
        job = await job_repository.fetch_job_detail(job_id)

        llm = await _get_llm()
        if llm is None:
            return _fallback_analysis(job["title"], job["company"]).model_dump()

        cache_key = _build_analysis_cache_key(
            user_id=user_id,
            job_id=job_id,
            user_profile=user_profile,
            job=job,
        )
        return await _run_cached_analysis(
            cache_key=cache_key,
            llm=llm,
            query_text=query_text,
            job=job,
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Analyze job error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="공고 분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def close_resources() -> None:
    global _last_cache_sweep_at, _llm
    _llm = None
    async with _analysis_cache_lock:
        _analysis_cache.clear()
        _last_cache_sweep_at = 0.0

    async with _analysis_inflight_lock:
        tasks = list(_analysis_inflight.values())
        _analysis_inflight.clear()

    for task in tasks:
        if not task.done():
            task.cancel()

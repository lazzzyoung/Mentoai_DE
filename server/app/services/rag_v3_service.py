from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from fastapi import HTTPException

from server.app.core.config import OPENAI_API_KEY, OPENAI_MODEL, RECOMMENDATION_LIMIT
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
    return max(60, min(95, int(round(55 + (bounded * 45)))))


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


async def recommend_jobs_list(user_id: int) -> RecommendationListResponse:
    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        query_text = _build_user_query_text(user_profile)

        ranked_jobs = await retrieve_jobs(query_text, limit=RECOMMENDATION_LIMIT)

        recommendations = [
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
                model=OPENAI_MODEL,
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
        current_score=68,
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


async def analyze_job_detail(job_id: int, user_id: int) -> dict[str, Any]:
    try:
        user_info = await fetch_user_info(user_id)
        user_profile = _to_user_profile(user_info)
        query_text = _build_user_query_text(user_profile)
        job = await job_repository.fetch_job_detail(job_id)

        llm = await _get_llm()
        if llm is None:
            return _fallback_analysis(job["title"], job["company"]).model_dump()

        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        parser = JsonOutputParser(pydantic_object=DetailedAnalysisResponse)
        prompt = ChatPromptTemplate.from_template(
            """
            당신은 채용 면접관입니다. 사용자 프로필과 공고를 비교해 실천 가능한 조언을 제공하세요.
            [사용자] {user_specs}
            [공고] {company} / {title} / {content}

            아래 JSON 포맷으로만 답변하세요.
            {format_instructions}
            """
        )

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

        if not isinstance(result, dict):
            result = _fallback_analysis(job["title"], job["company"]).model_dump()

        result["job_title"] = job["title"]
        result["company_name"] = job["company"]
        return result
    except HTTPException:
        raise
    except Exception as error:
        logger.error("Analyze job error: %s", error)
        raise HTTPException(
            status_code=500,
            detail="공고 분석 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        ) from error


async def close_resources() -> None:
    global _llm
    _llm = None

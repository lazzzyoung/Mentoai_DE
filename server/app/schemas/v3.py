from typing import List

from pydantic import BaseModel, Field


class JobSummary(BaseModel):
    job_id: int
    company: str
    title: str
    match_score: int = Field(description="적합도 점수 (60~100)")
    max_score: int = Field(default=100, description="만점 기준")
    reason: str = Field(description="추천 이유 한 줄 요약")


class JobSummaryList(BaseModel):
    jobs: List[JobSummary]


class RecommendationListResponse(BaseModel):
    user_name: str
    recommendations: List[JobSummary]


class ActionItem(BaseModel):
    category: str
    item_name: str
    description: str
    expected_score_up: int


class DetailedAnalysisResponse(BaseModel):
    job_title: str
    company_name: str
    current_score: int
    max_score: int = 100
    analysis_summary: str
    required_tech_stack: List[str]
    action_plan: List[ActionItem]
    interview_tip: str

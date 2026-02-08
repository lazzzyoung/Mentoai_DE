from typing import List

from pydantic import BaseModel, Field


class JobRecommendation(BaseModel):
    id: int
    company: str
    title: str


class GapItem(BaseModel):
    skill: str
    score_impact: int
    action_guide: str


class RoadmapStep(BaseModel):
    step_name: str
    description: str


class AnalysisResult(BaseModel):
    current_score: int
    summary: str
    gap_analysis: List[GapItem]
    roadmap: List[RoadmapStep]


class RoadmapResponse(BaseModel):
    user_name: str
    recommended_jobs: List[JobRecommendation]
    analysis_result: AnalysisResult


class JobSummary(BaseModel):
    job_id: int
    company: str
    title: str
    match_score: int = Field(description="적합도 점수 (60~100)")
    max_score: int = Field(default=100, description="만점 기준")
    reason: str = Field(description="추천 이유 한 줄 요약")


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

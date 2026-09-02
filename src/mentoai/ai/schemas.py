from pydantic import BaseModel, Field


class UserSummary(BaseModel):
    id: int
    username: str
    desired_job: str
    career_years: int


class JobSummary(BaseModel):
    job_id: int
    company: str
    title: str
    source: str | None = None
    career: str | None = Field(default=None, description="예: '3~7년' 또는 '신입 가능'")
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list, description="사용자 보유 스킬과 일치한 스킬")
    match_score: int = Field(description="적합도 점수 (40~99)")
    max_score: int = Field(default=100, description="만점 기준")
    reason: str = Field(description="추천 이유 한 줄 요약")


class RecommendationListResponse(BaseModel):
    user_name: str
    recommendations: list[JobSummary]


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
    required_tech_stack: list[str]
    action_plan: list[ActionItem]
    interview_tip: str

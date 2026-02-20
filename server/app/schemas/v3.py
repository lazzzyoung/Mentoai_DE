from pydantic import BaseModel, Field


class JobSummary(BaseModel):
    job_id: int
    company: str
    title: str
    match_score: int = Field(description="적합도 점수 (0~100)")
    max_score: int = Field(default=100, description="만점 기준")
    reason: str = Field(description="추천 이유 한 줄 요약")


class JobSummaryList(BaseModel):
    jobs: list[JobSummary]


class UserProfileSummary(BaseModel):
    desired_job: str = Field(description="회원 가입 시 입력한 희망 직무")
    career_years: int = Field(default=0, description="경력(년)")
    skills: list[str] = Field(default_factory=list, description="보유 기술 스택")


class RecommendationListResponse(BaseModel):
    user_id: int
    user_name: str
    user_profile: UserProfileSummary
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


class QuickLoginRequest(BaseModel):
    user_name: str = Field(min_length=1, description="사용자 입력 이름")
    desired_job: str = Field(default="미입력", description="희망 직무")
    career_years: int = Field(default=0, ge=0, description="경력(년)")
    skills: list[str] = Field(default_factory=list, description="보유 기술 스택")


class QuickLoginResponse(BaseModel):
    user_id: int
    user_name: str
    user_profile: UserProfileSummary

from typing import List

from pydantic import BaseModel


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


class AnalysisResultV2(BaseModel):
    current_score: int
    summary: str
    gap_analysis: List[GapItem]
    roadmap: List[RoadmapStep]


class RoadmapResponseV2(BaseModel):
    user_name: str
    recommended_jobs: List[JobRecommendation]
    analysis_result: AnalysisResultV2

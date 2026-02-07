from typing import List

from pydantic import BaseModel


class RoadmapResponseV1(BaseModel):
    user_name: str
    recommended_jobs: List[str]
    analysis_result: str

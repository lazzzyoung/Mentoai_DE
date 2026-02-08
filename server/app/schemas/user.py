from typing import List

from pydantic import BaseModel


class UserSpecResponse(BaseModel):
    user_id: int
    desired_job: str
    career_years: int
    education: str
    skills: List[str]
    certificates: List[str]

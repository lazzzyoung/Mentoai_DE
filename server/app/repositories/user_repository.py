from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from server.app.models.user import User, UserSpec


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch_user_profile(self, user_id: int) -> dict[str, Any] | None:
        query = (
            select(UserSpec, User)
            .join(User)
            .where(UserSpec.user_id == user_id)
        )
        result = await self.session.exec(query)
        row = result.first()
        if row is None:
            return None

        user_spec, user = row
        return {
            "username": user.username,
            "desired_job": user_spec.desired_job,
            "career_years": user_spec.career_years,
            "skills": user_spec.skills,
        }

    async def fetch_user_specs(self, user_id: int) -> dict[str, Any] | None:
        query = select(UserSpec).where(UserSpec.user_id == user_id)
        result = await self.session.exec(query)
        user_spec = result.first()
        if user_spec is None:
            return None

        return {
            "spec_id": user_spec.spec_id,
            "user_id": user_spec.user_id,
            "desired_job": user_spec.desired_job or "",
            "career_years": int(user_spec.career_years or 0),
            "education": user_spec.education or "",
            "skills": list(user_spec.skills or []),
            "certificates": list(user_spec.certificates or []),
            "updated_at": user_spec.updated_at,
        }

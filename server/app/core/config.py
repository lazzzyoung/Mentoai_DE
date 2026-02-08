import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    qdrant_host: str
    qdrant_port: int
    collection_name: str
    google_api_key: str | None

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql://airflow:airflow@postgres:5432/mentoai"
        ),
        qdrant_host=os.getenv("QDRANT_HOST", "mentoai-qdrant"),
        qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
        collection_name=os.getenv("QDRANT_COLLECTION_NAME", "career_jobs"),
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

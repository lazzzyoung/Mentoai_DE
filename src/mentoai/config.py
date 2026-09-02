from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://mentoai:mentoai@localhost:5433/mentoai"

    google_api_key: str = ""
    gemini_model: str = "gemini-3-flash-preview"

    embedding_provider: str = "fastembed"  # fastembed | gemini
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_cache_dir: str = ".models"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1024

    wanted_base_url: str = "https://www.wanted.co.kr"
    wanted_job_group_id: str = "518"  # 개발 직군
    wanted_job_ids: str = "655"  # 데이터 엔지니어
    scrape_max_items: int = 120
    scrape_delay_seconds: float = 0.4

    schedule_enabled: bool = False
    schedule_cron: str = "0 9,16 * * *"
    schedule_timezone: str = "Asia/Seoul"

    recommend_top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()

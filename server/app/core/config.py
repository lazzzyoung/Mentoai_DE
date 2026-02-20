from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(DATA_DIR / "mentoai.db")))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", os.getenv("OPENAI_MODEL", "gpt-5-mini"))
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", OPENAI_DEFAULT_MODEL)
OPENAI_PROMPT_CACHE_KEY_PREFIX = os.getenv("OPENAI_PROMPT_CACHE_KEY_PREFIX", "mentoai-job-analysis-v1")
OPENAI_PROMPT_CACHE_RETENTION = os.getenv("OPENAI_PROMPT_CACHE_RETENTION", "in_memory")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BM-K/KoSimCSE-roberta-multitask")

WANTED_BASE_URL = os.getenv("WANTED_BASE_URL", "https://www.wanted.co.kr")
TARGET_JOB_GROUP = os.getenv("TARGET_JOB_GROUP") or ""
TARGET_JOB_ID = os.getenv("TARGET_JOB_ID") or ""

CRAWLER_INTERVAL_MINUTES = int(os.getenv("CRAWLER_INTERVAL_MINUTES", "360"))

RETRIEVAL_ALPHA = float(os.getenv("RETRIEVAL_ALPHA", "0.45"))
RANK_RETRIEVAL_WEIGHT = float(os.getenv("RANK_RETRIEVAL_WEIGHT", "0.7"))
RECOMMENDATION_LIMIT = int(os.getenv("RECOMMENDATION_LIMIT", "20"))
CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "50"))
ANALYSIS_CACHE_TTL_SECONDS = int(os.getenv("ANALYSIS_CACHE_TTL_SECONDS", "900"))
ANALYSIS_CACHE_MAX_ENTRIES = int(os.getenv("ANALYSIS_CACHE_MAX_ENTRIES", "300"))
ANALYSIS_CACHE_SWEEP_SECONDS = int(os.getenv("ANALYSIS_CACHE_SWEEP_SECONDS", "60"))

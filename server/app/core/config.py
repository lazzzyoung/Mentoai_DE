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

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BM-K/KoSimCSE-roberta-multitask")

WANTED_BASE_URL = os.getenv("WANTED_BASE_URL", "https://www.wanted.co.kr")
TARGET_JOB_GROUP = os.getenv("TARGET_JOB_GROUP") or ""
TARGET_JOB_ID = os.getenv("TARGET_JOB_ID") or ""

CRAWLER_INTERVAL_MINUTES = int(os.getenv("CRAWLER_INTERVAL_MINUTES", "360"))

RETRIEVAL_ALPHA = float(os.getenv("RETRIEVAL_ALPHA", "0.45"))
RECOMMENDATION_LIMIT = int(os.getenv("RECOMMENDATION_LIMIT", "20"))
CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "50"))

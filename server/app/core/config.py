import os

from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://airflow:airflow@postgres:5432/mentoai")
QDRANT_HOST = os.getenv("QDRANT_HOST", "mentoai-qdrant")
QDRANT_URL = f"http://{QDRANT_HOST}:6333"
COLLECTION_NAME = "career_jobs"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

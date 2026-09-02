-- MentoAI 초기 스키마: medallion 구조가 SQLite 테이블로 녹아 있다.
-- bronze_raw_postings (원본 보존) -> silver_jobs (정제) -> silver_job_embeddings (벡터 BLOB)
--
-- 원본 PostgreSQL 스키마와의 대응:
--   bronze.raw_postings  -> bronze_raw_postings (jsonb payload -> TEXT JSON)
--   silver.jobs          -> silver_jobs        (text[] skill_tags -> TEXT JSON 배열)
--   silver.job_embeddings-> silver_job_embeddings (vector(1024) -> float32 BLOB)
-- 타임스탬프는 RFC3339Nano UTC 문자열로 저장한다(문자열 비교 == 시간 비교).

-- 서비스 사용자
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS user_specs (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    desired_job TEXT NOT NULL,
    career_years INTEGER NOT NULL DEFAULT 0,
    skills TEXT NOT NULL DEFAULT '[]'
);

-- Bronze: 수집 원본 (JSON) 보존
CREATE TABLE IF NOT EXISTS bronze_raw_postings (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);

-- Silver: 소스 통합 정제 공고
CREATE TABLE IF NOT EXISTS silver_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    company TEXT,
    position TEXT,
    location TEXT,
    intro TEXT,
    main_tasks TEXT,
    requirements TEXT,
    preferred_points TEXT,
    benefits TEXT,
    employment_type TEXT,
    is_newbie INTEGER,
    annual_from INTEGER,
    annual_to INTEGER,
    due_time TEXT,
    skill_tags TEXT NOT NULL DEFAULT '[]',
    pay TEXT,
    link TEXT,
    deadline TEXT,
    full_text TEXT NOT NULL DEFAULT '',
    collected_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_silver_jobs_collected_at ON silver_jobs (collected_at DESC);

-- Gold: 임베딩 (float32 BLOB, 검색은 애플리케이션 코사인)
CREATE TABLE IF NOT EXISTS silver_job_embeddings (
    job_id INTEGER PRIMARY KEY REFERENCES silver_jobs(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    model TEXT NOT NULL,
    embedded_at TEXT NOT NULL
);

-- LLM 상세 분석 캐시: (공고, 사용자, 모델) 조합은 1회만 Gemini 호출
CREATE TABLE IF NOT EXISTS analysis_cache (
    job_id INTEGER NOT NULL REFERENCES silver_jobs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (job_id, user_id, model)
);

-- 파이프라인 실행 이력
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    scraped INTEGER,
    silver_upserted INTEGER,
    embedded INTEGER,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);

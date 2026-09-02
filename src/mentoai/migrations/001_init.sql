-- MentoAI 초기 스키마: medallion 구조가 Postgres 스키마로 녹아 있다.
-- bronze.raw_postings (원본 보존) -> silver.jobs (정제) -> silver.job_embeddings (벡터)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;

-- 서비스 사용자
CREATE TABLE IF NOT EXISTS users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS user_specs (
    user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    desired_job text NOT NULL,
    career_years int NOT NULL DEFAULT 0,
    skills text[] NOT NULL DEFAULT '{}'
);

-- Bronze: 수집 원본 (JSONB) 보존
CREATE TABLE IF NOT EXISTS bronze.raw_postings (
    source text NOT NULL,
    source_id text NOT NULL,
    payload jsonb NOT NULL,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    collected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_id)
);

-- Silver: 소스 통합 정제 공고
CREATE TABLE IF NOT EXISTS silver.jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL,
    source_id text NOT NULL,
    company text,
    position text,
    location text,
    intro text,
    main_tasks text,
    requirements text,
    preferred_points text,
    benefits text,
    employment_type text,
    is_newbie boolean,
    annual_from int,
    annual_to int,
    due_time text,
    skill_tags text[] NOT NULL DEFAULT '{}',
    pay text,
    link text,
    deadline text,
    full_text text NOT NULL DEFAULT '',
    collected_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_collected_at ON silver.jobs (collected_at DESC);

-- Gold: 임베딩 (bge-m3 dense 1024차원, HNSW cosine)
CREATE TABLE IF NOT EXISTS silver.job_embeddings (
    job_id bigint PRIMARY KEY REFERENCES silver.jobs(id) ON DELETE CASCADE,
    embedding vector(1024) NOT NULL,
    model text NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_embeddings_hnsw
    ON silver.job_embeddings USING hnsw (embedding vector_cosine_ops);

-- LLM 상세 분석 캐시: (공고, 사용자, 모델) 조합은 1회만 Gemini 호출
CREATE TABLE IF NOT EXISTS analysis_cache (
    job_id bigint NOT NULL REFERENCES silver.jobs(id) ON DELETE CASCADE,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model text NOT NULL,
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, user_id, model)
);

-- 파이프라인 실행 이력
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    scraped int,
    silver_upserted int,
    embedded int,
    status text NOT NULL DEFAULT 'running',
    error text
);

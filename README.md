# MentoAI DE

MentoAI는 사용자 스펙(희망 직무, 경력, 보유 기술)과 채용 공고를 비교 분석해 맞춤형 커리어 로드맵을 제공하는 서비스입니다.  
이 저장소는 데이터 엔지니어링 파이프라인(Kafka, Spark, Airflow)과 RAG API(FastAPI, Qdrant, Gemini)를 함께 포함합니다.

## 프로젝트 설명

이 프로젝트는 "채용 공고 데이터 수집/정제 파이프라인"과 "사용자 맞춤 추천 API"를 하나로 연결한 엔드투엔드 시스템입니다.

- 문제 정의
채용 공고 원문은 소스마다 형식이 달라 바로 추천에 쓰기 어렵고, 사용자 스펙과의 정량 비교가 어렵습니다.
- 해결 방식
Airflow + Spark로 공고를 표준 스키마로 정제한 뒤, 임베딩/벡터 검색(Qdrant)과 LLM(Gemini)을 결합해 추천 점수와 액션 플랜을 생성합니다.
- 이 저장소의 범위
데이터 수집(Kafka producer), ETL(Bronze/Silver/Gold), 벡터 적재(Qdrant), FastAPI 기반 RAG API까지 포함합니다.
- 기대 결과
단순 키워드 매칭이 아니라, 사용자 경력/기술 대비 공고 적합도와 보완 학습 경로를 함께 제공합니다.

## System Architecture

```text
[Data Ingestion]                       [Data Processing]
Wanted / Work24 -> Kafka -> Spark ETL -> S3 (Bronze)
                                       -> PostgreSQL (Silver)
                                       -> Qdrant (Gold)
                          ^
                          |
                      Airflow DAG

[Service Layer]
User <-> FastAPI (RAG) <-> Qdrant
                    \-> Gemini (LLM)
```

## Key Features

1. Automated ETL Pipeline
- Airflow DAG로 수집 -> 정제 -> 벡터 적재를 자동 실행
- `mentoai_pipeline`에서 `run_kafka_producer -> spark_ingest_bronze -> spark_process_silver -> spark_upsert_gold` 순서로 동작

2. Unified Job Schema
- Wanted / Work24 공고를 하나의 정규화 스키마로 통합
- 중복 제거(`source:source_id` 기반) 후 Silver 적재

3. Semantic Search + RAG
- `BM-K/KoSimCSE-roberta-multitask` 임베딩으로 공고 벡터화
- Qdrant 유사도 검색 + Gemini로 추천 점수/상세 분석 생성

## Tech Stack

| Layer | Stack | Purpose |
| --- | --- | --- |
| Orchestration | Apache Airflow 2.8 | DAG 스케줄링, 배치 파이프라인 오케스트레이션 |
| Streaming | Apache Kafka 3.8 | 수집 데이터 이벤트 버퍼링 |
| Processing | Apache Spark 3.5 (PySpark) | Bronze/Silver/Gold ETL |
| Storage (Bronze) | AWS S3 (Parquet) | Raw 이벤트 적재 |
| Storage (Silver) | PostgreSQL 13 | 정제 데이터 저장 |
| Storage (Gold) | Qdrant 1.13 | 벡터 검색 인덱스 |
| API | FastAPI + Uvicorn | RAG API 제공 |
| LLM / RAG | Gemini (`langchain-google-genai`), LangChain | 추천/분석 응답 생성 |
| Embedding | `BM-K/KoSimCSE-roberta-multitask` | 공고/질의 벡터화 |
| Package/Run | `uv` | 의존성 그룹 관리(`airflow`, `spark`, `server`, `dev`) |
| Infra | Docker Compose | 로컬 통합 실행 환경 |

## Repository Structure

```text
Mentoai_DE/
├── dags/                     # Airflow DAG
├── kafka/                    # 채용 공고 수집 producer
├── spark/                    # Bronze/Silver/Gold Spark jobs
├── server/app/               # FastAPI + RAG 서비스
├── tests/                    # pytest 테스트
├── infra/                    # docker-compose 및 Dockerfile
├── pyproject.toml            # uv dependency groups
└── .env.example              # 환경 변수 템플릿
```

## Development Setup

### 1) Prerequisites

- Docker Desktop + Docker Compose v2
- Python 3.11+
- `uv` (dependency and task runner)
- AWS S3 접근 키
- Google Gemini API Key

`uv`가 없으면 설치:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

개발용 의존성(테스트/poe 포함) 설치:

```bash
uv sync --group dev
```

### 2) Environment Variables

```bash
cp .env.example .env
```

필수 항목:

| Variable | Description |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini 호출 키 |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` | Bronze 저장용 S3 접근 |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | Airflow 세션 보안 키 |
| `AIRFLOW_ADMIN_USERNAME`, `AIRFLOW_ADMIN_PASSWORD` | Airflow 관리자 계정 |

기본값이 있어도 환경에 맞춰 확인할 항목:

| Variable | Default | Notes |
| --- | --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` | Docker 네트워크 기준 |
| `KAFKA_TOPIC_NAME` | `career_raw` | 수집 토픽 |
| `DB_URL` | `jdbc:postgresql://postgres:5432/mentoai` | Spark JDBC |
| `DATABASE_URL` | `postgresql://airflow:airflow@postgres:5432/mentoai` | FastAPI DB |
| `QDRANT_HOST` | `mentoai-qdrant` | Docker 컨테이너명 |
| `QDRANT_COLLECTION_NAME` | `career_jobs` | Gold 컬렉션명 |

### 3) Start Infrastructure

기본 방식:

```bash
cd infra
docker compose up -d --build
```

`poe` 단축 명령:

```bash
uv run poe infra_up
```

주요 접속 주소:

- Airflow: `http://localhost:8081`
- FastAPI Swagger: `http://localhost:8000/docs`
- Kafka UI: `http://localhost:8080`
- Spark Master UI: `http://localhost:8082`
- Qdrant API: `http://localhost:6333`

## Quick Start (End-to-End)

### 1) Seed user tables

```bash
docker exec -it mentoai-postgres psql -U airflow -d mentoai
```

```sql
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_specs (
    spec_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    desired_job VARCHAR(100),
    career_years INT DEFAULT 0,
    education VARCHAR(100),
    skills TEXT[],
    certificates TEXT[],
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (username, email)
VALUES ('강태영', 'tang0923@khu.ac.kr')
ON CONFLICT (email) DO NOTHING;

INSERT INTO user_specs (
    user_id, desired_job, career_years, education, skills, certificates
) VALUES (
    1, 'Data Engineer', 0, '학사',
    ARRAY['Python', 'Spark', 'Kafka', 'Airflow'],
    ARRAY['정보처리기사', 'SQLD']
)
ON CONFLICT DO NOTHING;
```

### 2) Run Airflow pipeline

1. `http://localhost:8081` 접속 후 관리자 계정 로그인
2. `mentoai_pipeline` DAG unpause
3. Trigger 실행
4. 다음 태스크 성공 확인
- `run_kafka_producer`
- `spark_ingest_bronze`
- `spark_process_silver`
- `spark_upsert_gold`

### 3) Test API

```bash
curl -X POST "http://localhost:8000/api/v3/jobs/recommend/1" \
  -H "accept: application/json" \
  -d ''

curl -X POST "http://localhost:8000/api/v3/jobs/{JOB_ID}/analyze/1" \
  -H "accept: application/json" \
  -d ''
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Health check |
| GET | `/api/v1/test/gemini` | Gemini 연결 테스트 |
| GET | `/api/v1/users/{user_id}/specs` | 사용자 스펙 조회 |
| POST | `/api/v1/curation/roadmap/{user_id}` | V1 로드맵 생성 |
| POST | `/api/v2/curation/roadmap/{user_id}` | V2 구조화 로드맵 생성 |
| POST | `/api/v3/jobs/recommend/{user_id}` | 추천 공고 목록 + 적합도 점수 |
| POST | `/api/v3/jobs/{job_id}/analyze/{user_id}` | 공고 상세 분석 |

## Local Development Workflow

### Dependency groups (`uv`)

```bash
# 서버 개발
uv sync --group server

# Spark 스크립트 실행용
uv sync --group spark

# Airflow/DAG 개발용
uv sync --group airflow

# 테스트/정적 분석 포함 전체 개발 환경
uv sync --group dev
```

### Common Poe Tasks

`poe`는 자주 쓰는 명령을 짧게 실행하기 위한 태스크 러너입니다.

```bash
# 실행 형식
uv run poe <task_name>
```

| Category | Task | Description |
| --- | --- | --- |
| Setup | `setup_env` | `.env`가 없으면 `.env.example`로 생성 |
| Setup | `sync_dev` | 전체 개발 의존성 설치 |
| Setup | `sync_server` | API 개발용 의존성 설치 |
| Setup | `sync_spark` | Spark 스크립트 의존성 설치 |
| Setup | `sync_airflow` | Airflow/DAG 의존성 설치 |
| Infra | `infra_up` | `infra/docker-compose.yml` 전체 기동 |
| Infra | `infra_down` | 인프라 종료/정리 |
| Infra | `infra_restart` | 인프라 재시작 |
| Infra | `infra_ps` | 컨테이너 상태 확인 |
| Infra | `infra_logs` | compose 로그 팔로우 |
| API | `api_dev` | FastAPI 로컬 개발 서버 실행(reload) |
| Producer | `producer_wanted` | Wanted 수집 producer 실행 |
| Producer | `producer_daily` | Work24 일일 수집 producer 실행 |
| Producer | `producer_backfill` | Work24 백필 producer 실행(기본 1~3페이지) |
| Spark | `spark_bronze` | Bronze job 실행 |
| Spark | `spark_silver` | Silver job 실행 |
| Spark | `spark_gold` | Gold job 실행 |
| Quality | `lint`, `lint_fix` | Ruff 린트/자동수정 |
| Quality | `format`, `format_check` | Ruff 포맷/검증 |
| Quality | `type` | 타입 검사(`ty`) |
| Quality | `test`, `test_kafka`, `test_spark` | pytest 테스트 |
| Quality | `check` | `lint + type + test` 순차 실행 |

### Run FastAPI locally (without docker ai-server)

로컬에서 API만 단독 실행할 경우 `.env`의 `DATABASE_URL`, `QDRANT_HOST`를 로컬 주소로 바꿔야 합니다.

예시:

```dotenv
DATABASE_URL=postgresql://airflow:airflow@localhost:5432/mentoai
QDRANT_HOST=localhost
```

실행:

```bash
uv run uvicorn server.app.main:app --host 0.0.0.0 --port 8000 --reload

# or
uv run poe api_dev
```

### Run producer manually

```bash
uv run python kafka/producer_wanted.py
uv run python kafka/producer_recruit24_daily.py
uv run python kafka/producer_recruit24_backfill.py 1 3

# or
uv run poe producer_wanted
uv run poe producer_daily
uv run poe producer_backfill
```

## Data Pipeline Details

1. Ingestion (Kafka)
- Wanted / Work24 scraper가 raw 메시지를 `career_raw` 토픽으로 전송

2. Bronze (S3)
- `spark/job_ingest_bronze.py`가 Kafka 스트림을 Parquet로 저장
- 경로: `s3a://<S3_BUCKET_NAME>/bronze/career_raw/`

3. Silver (PostgreSQL)
- `spark/job_process_silver.py`가 메시지를 통합 스키마로 정제
- `source + source_id` 기준 중복 제거 후 `career_jobs` 적재

4. Gold (Qdrant)
- `spark/job_upsert_gold.py`가 임베딩 생성 후 `career_jobs` 컬렉션 upsert
- payload에 `company`, `position`, `full_text` 저장

## Test and Quality

```bash
uv sync --group dev
uv run poe test
uv run poe lint
uv run poe format
uv run poe type
uv run poe check
```

## DAG List

| DAG ID | Schedule | Purpose |
| --- | --- | --- |
| `mentoai_pipeline` | `0 9,16 * * *` | E2E 배치 파이프라인 |
| `producer_daily_dag` | `0 9 * * *` | Work24 일일 수집 |
| `producer_backfill_dag` | manual | Work24 과거 페이지 백필 |

## Troubleshooting

1. Airflow 로그인 후 권한 오류
- 원인: 관리자 초기화 미완료 또는 설정 누락
- 대응: `airflow-init` 서비스 실행 로그 확인, 관리자 계정 재생성

2. Silver 테이블이 비어 있음
- 원인: Bronze 데이터 미적재 또는 S3 경로/권한 오류
- 대응: `s3a://<bucket>/bronze/career_raw/` 파일 존재 확인 후 `spark_process_silver` 재실행

3. 추천 응답에서 회사/포지션이 `미상`으로 출력됨
- 원인: Qdrant payload 필드 누락
- 대응: `company`, `position`, `full_text` 필드 upsert 여부 확인

4. 로컬 API 실행 시 DB/Qdrant 연결 실패
- 원인: Docker 내부 호스트명(`postgres`, `mentoai-qdrant`)을 로컬에서 그대로 사용
- 대응: `.env`를 `localhost` 기준으로 분리해서 사용

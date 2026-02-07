# MentoAI: Personalized AI Career Roadmap Service

MentoAI는 사용자 스펙(희망 직무, 경력, 보유 기술)과 채용 공고를 비교 분석해 맞춤형 커리어 로드맵을 제공하는 RAG 기반 서비스입니다.  
데이터 엔지니어링 파이프라인(Kafka, Spark, Airflow)과 벡터 검색(Qdrant), LLM(Gemini)을 결합해 추천 + 상세 컨설팅을 제공합니다.

## System Architecture

```text
[Data Ingestion]                       [Data Processing]
Job Sites (Wanted 등) -> Kafka -> Spark ETL -> S3 (Bronze)
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
- Airflow + Spark 기반으로 Bronze/Silver/Gold 파이프라인 자동화
- `mentoai_pipeline` DAG에서 수집 -> 정제 -> 벡터 적재를 순차 실행

2. Semantic Search
- `BM-K/KoSimCSE-roberta-multitask` 임베딩으로 공고 텍스트 벡터화
- Qdrant 유사도 검색으로 문맥 기반 직무 매칭

3. RAG Career Consulting
- Gemini 기반으로 추천 목록 점수화 + 상세 액션 플랜 생성
- 단순 추천이 아닌 부족 역량 분석과 학습 가이드 제공

## Medallion Pipeline

1. Ingestion (Kafka)
- `kafka/producer_wanted.py`가 채용 공고를 수집해 `career_raw` 토픽으로 전송

2. Bronze (S3)
- `spark/job_ingest_bronze.py`가 Kafka raw 이벤트를 S3 Parquet로 저장

3. Silver (PostgreSQL)
- `spark/job_process_silver.py`가 raw 데이터를 정제해 `career_jobs` 테이블 적재

4. Gold (Qdrant)
- `spark/job_upsert_gold.py`가 임베딩을 생성해 Qdrant 컬렉션(`career_jobs`)에 upsert

5. Service (FastAPI)
- `server/app/main.py`가 추천/상세 분석 API 제공

## Project Structure

```text
Mentoai_DE/
├── pyproject.toml
├── .python-version
├── dags/
│   ├── mentoai_pipeline.py
│   ├── producer_daily_dag.py
│   └── producer_backfill_dag.py
├── kafka/
│   ├── producer_wanted.py
│   ├── producer_recruit24_daily.py
│   ├── producer_recruit24_backfill.py
│   └── utils/
│       ├── wanted_scraper.py
│       └── recruit24_scraper.py
├── spark/
│   ├── job_ingest_bronze.py
│   ├── job_process_silver.py
│   ├── job_upsert_gold.py
│   └── utils/
│       ├── spark_session.py
│       ├── text_cleaner.py
│       ├── readers.py
│       └── writers.py
├── server/
│   └── app/
│       └── main.py
├── infra/
│   ├── docker-compose.yml
│   ├── airflow/
│   ├── spark/
│   └── server/
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | 서버 헬스 체크 |
| GET | `/api/v1/test/gemini` | Gemini 연결 테스트 |
| GET | `/api/v1/users/{user_id}/specs` | 사용자 스펙 조회 |
| POST | `/api/v1/curation/roadmap/{user_id}` | V1 로드맵 생성 |
| POST | `/api/v2/curation/roadmap/{user_id}` | V2 구조화 로드맵 |
| POST | `/api/v3/jobs/recommend/{user_id}` | 추천 공고 목록 + 점수 |
| POST | `/api/v3/jobs/{job_id}/analyze/{user_id}` | 공고 상세 컨설팅 |

## Prerequisites

- Docker / Docker Compose
- `uv` (Python 의존성/실행 관리)
- Python 3.11+ (로컬 스크립트 직접 실행 시)
- 필수 키/접근 정보
  - Google Gemini API Key
  - AWS S3 Access Key

## Dependency Management (uv)

이 프로젝트는 `requirements.txt` 대신 루트 `pyproject.toml`의 dependency group을 사용합니다.

- `server`: FastAPI + LangChain + Qdrant
- `spark`: Spark 보조 파이썬 의존성 + `torch`
- `airflow`: DAG 실행 및 수집/연동 의존성
- `dev`: 테스트/정적 분석용

예시:

```bash
# lockfile 생성/갱신
uv lock

# server 개발 환경
uv sync --group server

# Spark 실행 스크립트용 환경
uv sync --group spark

# Airflow/DAG 로컬 실행용 환경
uv sync --group airflow
```

## Quick Start

### 1) `.env` 설정

프로젝트 루트(`README.md`와 같은 위치)에 `.env` 파일을 생성하고 최소 항목을 채워주세요.

```dotenv
GOOGLE_API_KEY=your_gemini_key

AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=your_bucket_name

KAFKA_BOOTSTRAP_SERVERS=kafka:29092
KAFKA_TOPIC_NAME=career_raw

WANTED_BASE_URL=https://www.wanted.co.kr
TARGET_JOB_GROUP=518
TARGET_JOB_ID=655

DB_URL=jdbc:postgresql://postgres:5432/mentoai
DB_USER=airflow
DB_PASSWORD=airflow

DATABASE_URL=postgresql://airflow:airflow@postgres:5432/mentoai
QDRANT_HOST=mentoai-qdrant
```

### 2) 인프라 실행

```bash
cd infra
docker compose up -d --build
```

`infra/*/Dockerfile`은 내부에서 `uv`로 group 의존성을 설치합니다.

### 3) 사용자 테이블/샘플 데이터 준비

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
);
```

### 4) Airflow에서 파이프라인 실행

1. 브라우저에서 `http://localhost:8081` 접속
2. `admin / admin` 로그인
3. `mentoai_pipeline` DAG를 Unpause
4. Trigger 실행 후 `run_kafka_producer -> spark_ingest_bronze -> spark_process_silver -> spark_upsert_gold` 성공 확인

### 5) API 테스트

Swagger: `http://localhost:8000/docs`

```bash
curl -X POST "http://localhost:8000/api/v3/jobs/recommend/1" \
  -H "accept: application/json" \
  -d ''

curl -X POST "http://localhost:8000/api/v3/jobs/{JOB_ID}/analyze/1" \
  -H "accept: application/json" \
  -d ''
```

## Tech Stack

- Infrastructure: Docker Compose, Airflow
- Data: Kafka, Spark (PySpark)
- Storage: AWS S3, PostgreSQL, Qdrant
- AI/Backend: FastAPI, LangChain, Gemini, KoSimCSE
- Dependency Management: uv (`pyproject.toml` dependency groups)

## Troubleshooting Notes

1. Airflow 권한 오류 (RBAC)
- 현상: 로그인 후 권한 부족으로 페이지 접근 실패
- 대응: `airflow-init` 재실행 또는 관리자 유저 재생성

2. Postgres 데이터 휘발
- 현상: 컨테이너 재시작 후 데이터 유실
- 대응: `infra/postgres_data` 볼륨 마운트 유지 여부 확인

3. Silver 적재 누락
- 현상: Airflow 성공처럼 보이지만 `career_jobs`가 비어 있음
- 대응: S3 Bronze 경로(`s3a://<bucket>/bronze/career_raw/`) 데이터 유무 확인 후 `spark_process_silver` 재실행

4. Qdrant 메타데이터 누락
- 현상: 추천 응답의 회사/포지션이 `"미상"`으로 표기
- 대응: Qdrant payload 저장 필드(`company`, `position`, `full_text`) 확인

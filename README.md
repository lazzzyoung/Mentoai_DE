# MentoAI DE

MentoAI DE는 채용 공고 데이터를 수집/정제하고, 사용자 스펙 기반 추천 API를 제공하는 백엔드 저장소입니다.  
데이터 파이프라인(Kafka, Spark, Airflow)과 서비스 API(FastAPI, Qdrant, Gemini)를 함께 운영합니다.

## 문서

- 서비스/화면 설계: `DESIGN.md`
- 변경 이력: `CHANGELOG.md`

## 프로젝트 개요

- 채용 공고 원문을 표준 스키마로 정제해 검색/추천 품질을 높입니다.
- 사용자 스펙(희망 직무, 경력, 기술)과 공고를 비교해 적합도와 액션 플랜을 제공합니다.
- ETL과 API를 한 저장소에서 관리해 로컬 개발/검증 흐름을 단순화합니다.

## 시스템 아키텍처

```text
[Data Ingestion]                       [Data Processing]
Wanted / Work24 -> Kafka -> Spark ETL -> S3 (Bronze)
                                       -> PostgreSQL (Silver)
                                       -> Qdrant (Gold)
                          ^
                          |
                      Airflow DAG

[Service Layer]
Client <-> FastAPI <-> Qdrant
                \-> Gemini
```

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| API | FastAPI, Uvicorn |
| ORM/DB | SQLModel, SQLAlchemy AsyncSession, asyncpg, PostgreSQL |
| 벡터 검색 | Qdrant |
| LLM/RAG | Gemini, LangChain |
| 데이터 처리 | PySpark |
| 오케스트레이션 | Airflow |
| 스트리밍 | Kafka |
| 패키지/실행 | uv, Poe the Poet |
| 인프라 | Docker Compose |

## 저장소 구조

```text
Mentoai_DE/
├── dags/                    # Airflow DAG
├── infra/                   # docker-compose, Dockerfile
├── kafka/                   # 수집 프로듀서
├── server/app/              # FastAPI 앱
├── spark/                   # Spark ETL 작업
├── tests/                   # 테스트
├── pyproject.toml           # 의존성/poe task 정의
└── .env.example             # 환경 변수 템플릿
```

## 개발 환경 세팅

### 1) 사전 준비

- Docker Desktop (Compose v2 포함)
- Python 3.11+
- `uv`
- AWS S3 접근 정보
- Gemini API Key

`uv` 설치:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

의존성 설치:

```bash
uv sync --group dev
```

### 2) 환경 변수

```bash
cp .env.example .env
```

필수 항목:

- `GOOGLE_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `S3_BUCKET_NAME`
- `AIRFLOW__WEBSERVER__SECRET_KEY`
- `AIRFLOW_ADMIN_USERNAME`
- `AIRFLOW_ADMIN_PASSWORD`

주요 기본값:

- `KAFKA_BOOTSTRAP_SERVERS=kafka:29092`
- `KAFKA_TOPIC_NAME=career_raw`
- `DB_URL=jdbc:postgresql://postgres:5432/mentoai`
- `DATABASE_URL=postgresql://airflow:airflow@postgres:5432/mentoai`
- `QDRANT_HOST=mentoai-qdrant`
- `QDRANT_COLLECTION_NAME=career_jobs`

## 실행

### 인프라 실행 (Docker Compose)

```bash
uv run poe up
```

주요 주소:

- Airflow: `http://localhost:8081`
- FastAPI Docs: `http://localhost:8000/docs`
- Kafka UI: `http://localhost:8080`
- Spark Master UI: `http://localhost:8082`
- Qdrant: `http://localhost:6333`

### API만 로컬 실행

`.env`의 `DATABASE_URL`, `QDRANT_HOST`를 로컬 기준으로 바꿉니다.

예시:

```dotenv
DATABASE_URL=postgresql://airflow:airflow@localhost:5432/mentoai
QDRANT_HOST=localhost
```

실행:

```bash
uv run poe dev
```

일반 실행(no reload):

```bash
uv run poe run
```

호환용 alias:

```bash
uv run poe server_dev
uv run poe server_run
uv run poe api_dev
```

## API 엔드포인트

### 시스템/API

- `GET /health`: 헬스 체크
- `GET /api/v1/test/gemini`: Gemini 연결 확인
- `GET /api/v1/users/{user_id}/specs`: 사용자 스펙 조회
- `POST /api/v1/curation/roadmap/{user_id}`: 커리어 로드맵 생성
- `POST /api/v1/jobs/recommend/{user_id}`: 공고 추천
- `POST /api/v1/jobs/{job_id}/analyze/{user_id}`: 공고 상세 분석

### 웹 UI(서버 렌더링)

- `GET /`: 홈 화면 (JSON `Accept` 요청은 헬스 응답 호환)
- `GET /search`: 검색 화면
- `GET /profile`: 프로필 화면
- `POST /api/action`: HTMX 액션 응답
- `POST /api/web/action`: 구 경로 호환 alias

## 마이그레이션

적용:

```bash
uv run poe mig
```

리비전 생성(스키마 변경 감지):

```bash
uv run poe rev
```

`rev`는 내부적으로 `alembic revision --autogenerate`를 실행합니다.

## 자주 사용하는 Poe Tasks

| 분류 | Task | 설명 |
| --- | --- | --- |
| Setup | `env` | `.env` 생성 |
| Setup | `sync` | 개발용 전체 의존성 설치 |
| Setup | `sync_sr` | 서버 의존성 설치 |
| Setup | `sync_sp` | Spark 의존성 설치 |
| Setup | `sync_af` | Airflow 의존성 설치 |
| DB | `mig` | Alembic 적용 |
| DB | `rev` | Alembic autogenerate |
| API | `dev` | Uvicorn 개발 서버 실행(reload) |
| API | `run` | Uvicorn 서버 실행(no reload) |
| Infra | `up/down/restart/ps/logs` | Docker Compose 제어 |
| Producer | `pw/pd/pb` | Wanted/Work24 수집 실행 |
| Spark | `brz/slv/gld` | Spark ETL 작업 실행 |
| Quality | `lint`, `lint_fix` | Ruff 린트 |
| Quality | `format`, `format_check` | Ruff 포맷 |
| Quality | `type` | 타입 검사(`ty`) |
| Quality | `test`, `test_kafka`, `test_spark` | 테스트 실행 |
| Quality | `check` | `lint + type + test` |

기존 긴 이름 task(`setup_env`, `sync_dev`, `server_dev`, `db_migrate` 등)는 호환을 위해 유지됩니다.

## 품질 점검

```bash
uv run poe check
```

## CI

- GitHub Actions (`.github/workflows/ci.yml`)에서 push / pull_request 시 `uv run poe check`를 실행합니다.

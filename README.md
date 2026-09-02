# MentoAI: Personalized AI Career Roadmap Service

**MentoAI**는 사용자의 기술 스펙과 희망 직무를 분석하여, 최신 채용 공고 기반의 맞춤형 커리어 로드맵을 제공하는 AI 서비스입니다.

v2(과거) 아키텍처(Kafka + Spark + Airflow + S3 + Qdrant, 컨테이너 9개)를 **비용과 복잡도에 맞게 재설계**한 결과물입니다.
핵심 변경: **Medallion 구조를 Postgres 스키마로 내재화**하고, 벡터 검색은 **pgvector**, 임베딩은 **fastembed(로컬 ONNX)**, LLM은 **Gemini 구조화 출력**으로 통합했습니다. 컨테이너 9개 → **2개(api + postgres)**.

## 🏗️ Architecture

```
[Wanted API]  ─┐
[work24 리스트] ─┴─► httpx 스크래퍼 ─► bronze.raw_postings (JSONB 원본 보존)
                                        │ Polars 정제 (HTML 제거·소스 통합·중복 제거)
                                        ▼
                                    silver.jobs (통합 공고 스키마)
                                        │ 임베딩: fastembed e5-large (로컬) 또는 Gemini API
                                        ▼
                                    silver.job_embeddings (pgvector, HNSW cosine)
                                        │
             APScheduler (cron) ────────┤ 전체 파이프라인 스케줄링
                                        ▼
                       FastAPI ─► 추천: pgvector 유사도 + 휴리스틱 (LLM 0호출)
                                └► 상세 분석: Gemini 구조화 출력 + analysis_cache (1회만 호출)
```

## 🧰 Stack

| 영역 | 기술 | 비고 |
|---|---|---|
| 언어/패키징 | Python 3.12+, uv | 단일 lockfile, `uv run mentoai ...` |
| DB | PostgreSQL 17 + pgvector | `pgvector/pgvector:pg17` 이미지, Medallion = 스키마 |
| 마이그레이션 | 버전 관리 SQL (`src/mentoai/migrations/`) | 의존성 0개의 40줄 러너 |
| 수집 | httpx + BeautifulSoup | Wanted API / work24 리스트+상세 |
| 변환 | Polars | in-process, JVM 없음 |
| 임베딩 | fastembed e5-large / Gemini API (토글) | 둘 다 1024차원 → 컬럼/인덱스 불변 |
| LLM | google-genai (Gemini Flash) | Pydantic `response_schema` 구조화 출력, LangChain 제거 |
| API | FastAPI + uvicorn | v1 단일 버전 |
| UI | FastAPI가 직접 서빙하는 정적 페이지 | 모놀리식 — 빌드 도구·npm 없음, 바닐라 JS |
| PWA | manifest + 서비스워커 | 앱 설치 가능, 앱 셸 오프라인 캐시(데이터는 항상 네트워크), 오프라인 배너 |
| 스케줄링 | APScheduler | API 프로세스 내 cron |
| 품질 | ruff, ty, pytest | GitHub Actions CI |

## 🚀 Quick Start

```bash
cp .env.example .env          # GOOGLE_API_KEY 입력
make up                       # postgres + api 빌드/기동 (마이그레이션·시드 자동)
make pipeline                 # 전체 파이프라인 실행 (수집→정제→임베딩)
# 최초 1회는 e5-large 모델(~2.2GB)을 /data/models에 다운로드합니다
# 이후 브라우저에서 http://localhost:8000 접속 → 프로필 선택 → 추천/분석
# 관리자 화면: http://localhost:8000/admin (현황 대시보드·파이프라인 실행·데이터/인재/캐시 관리)
```

로컬 개발 (컨테이너 DB만 띄우고 코드는 호스트에서):

```bash
docker compose up -d postgres
uv sync
uv run mentoai migrate && uv run mentoai seed
uv run mentoai pipeline
uv run mentoai serve --reload
```

### CLI

```
mentoai migrate     # 마이그레이션 적용
mentoai seed        # 샘플 사용자 적재 (멱등)
mentoai status      # DB 현황·모델·스케줄·최근 실행 요약
mentoai scrape      # Bronze: 수집 → raw_postings
mentoai transform   # Silver: 정제 → jobs
mentoai embed       # Gold: 임베딩 (--force 전량 재계산)
mentoai pipeline    # 전체 실행 (pipeline_runs에 이력 기록)
mentoai jobs list/rm    # 공고 조회/삭제 (원본·임베딩·캐시 함께)
mentoai users list/set/rm   # 인재 조회/등록·수정/삭제
mentoai models      # 임베딩 모델 목록
mentoai switch-embedding   # 임베딩 모델 전환
mentoai serve       # API 서버
```

## 📡 API Endpoints

### 1. 기업 목록 추천
* **POST** `/api/v1/jobs/recommend/{user_id}`
* pgvector 유사도 검색 + 기술스택/경력 휴리스틱으로 상위 N개 공고와 적합도 점수를 **즉시(LLM 호출 없이)** 반환.

### 2. 상세 커리어 컨설팅
* **POST** `/api/v1/jobs/{job_id}/analyze/{user_id}`
* Gemini가 부족한 역량·액션 플랜·면접 팁을 구조화된 JSON으로 제공.
* 동일 (공고, 사용자, 모델) 조합은 `analysis_cache` 테이블에 캐시되어 **Gemini 호출 1회만** 발생.

### 3. 관리자 (`/admin` 페이지 + `/api/v1/admin/*`, CLI와 같은 로직 공유)
* 현황 대시보드(카운트·테이블 용량·모델·스케줄 다음 실행·진행 중 작업)
* 파이프라인 즉시 실행(백그라운드, 중복 409) + 실행 이력
* 공고 검색·삭제, 인재 등록/수정/삭제, 분석 캐시 관리
* 임베딩 운영: 모델 목록 조회·전환(백그라운드)·전량 재계산 (`mentoai status/jobs/users/embed --force`와 동일 기능)
* 데모용이라 인증이 없으므로 실서비스 노출 시 게이트웨이 인증 등 보호 필요

## 📂 Project Structure

```
mentoai_de/
├── compose.yaml               # postgres + api (2 서비스)
├── Dockerfile                 # uv 멀티스테이지 단일 이미지 (~300MB, PyTorch 없음)
├── src/mentoai/
│   ├── config.py              # pydantic-settings (.env)
│   ├── db/                    # asyncpg 풀 + pgvector 코덱 + SQL 마이그레이션 러너
│   ├── migrations/            # 001_init.sql (bronze/silver 스키마 + HNSW 인덱스)
│   ├── scrapers/              # wanted.py / work24.py (비동기 httpx)
│   ├── pipeline/              # bronze / silver(Polars) / gold(fastembed) / runner
│   ├── ai/                    # embeddings / gemini / recommend / analyzer / scoring
│   ├── api/                   # FastAPI 앱 + routes + APScheduler
│   ├── static/                # 모놀리식 UI (index/app + admin 페이지, 빌드 도구 없음)
│   └── cli.py                 # Typer CLI (uv run mentoai)
└── tests/                     # 정제·스코어링·API 단위 테스트 (DB 불필요)
```

## 🔎 임베딩 모델 선택 기록

v2의 KoSimCSE-roberta(2022, 768차원, korSTS 용 SimCSE)는 검색(retrieval) 목적 학습이 아니라는 한계가 있었다. 후보 비교 결과:

| 모델 | 차원 | 라이선스 | 비고 |
|---|---|---|---|
| BM-K/KoSimCSE-roberta (기존) | 768 | MIT | korSTS 강점, 검색 용도로는 구식 |
| **intfloat/multilingual-e5-large (기본)** | 1024 | MIT | 검색 학습된 다국어 모델, fastembed 네이티브 지원, PyTorch 불필요 |
| gemini-embedding-001 (옵션) | 1024 (조절) | API | MTEB 다국어 최상위권. `EMBEDDING_PROVIDER=gemini`로 전환 |
| jina-embeddings-v3 | 1024 | **CC-BY-NC** | 상용 서비스에 부적합해 제외 |
| BAAI/bge-m3 | 1024 | MIT | fastembed 0.8 지원 목록에 없음 (bge-m3 기반 KURE-v1은 한국어 검색 SOTA지만 ONNX 미제공) |
| nlpai-lab/KURE-v1 | 1024 | MIT | 한국어 검색 SOTA(bge-m3 파인튜닝). ONNX 직접 export 시 fastembed 대체 가능 — 향후 업그레이드 경로 |

모델 전환은 CLI 한 방이다 (`.env`는 자동 백업 후 갱신, 임베딩 테이블은 차원에 맞게 재생성되고 전량 재임베딩된다):

```bash
mentoai models                                  # 사용 가능한 모델 목록 + 현재 선택
mentoai switch-embedding --provider gemini --yes  # 로컬 → Gemini API
mentoai switch-embedding --provider fastembed \
  --model intfloat/multilingual-e5-large --yes    # 다시 로컬로
```

차원이 같은 전환이라 테이블 재생성이 필요 없더라도, 파이프라인의 gold 단계가 임베딩의 `model` 컬럼(provider 포함 식별자)을 검사해 **모델이 바뀌면 자동으로 재임베딩**한다. 즉 `.env`만 고치고 `mentoai pipeline`을 돌려도 안전하다.

## 📈 Why not Kafka/Spark/Airflow? (확장 설계서)

하루 수백 건 규모의 공고 데이터에 분산 스택은 순수 오버엔지니어링입니다. 각 기술의 재도입 시점을 명시해 둡니다.

| 신호 | 도입 기술 | 마이그레이션 경로 |
|---|---|---|
| 수집 소스 10개+ · 실시간성 요구 | Kafka/Redpanda | 스크래퍼 → producer 전환, consumer가 bronze에 적재 (bronze 인터페이스 불변) |
| 일일 수백만 건 | Spark/Flink | silver 변환만 교체 (normalize 함수 순수 → UDF 포팅 용이) |
| 파이프라인 20+ 태스크 · SLA 추적 | Airflow 3 / Dagster | runner.run_pipeline를 태스크로 래핑 (단계별 모듈이 이미 분리됨) |
| 벡터 수억 개 · 하이브리드 검색 | Qdrant | job_embeddings 테이블 → Qdrant 컬렉션 이관 (recommend 모듈만 교체) |

모든 계층이 인터페이스(scraper→bronze→silver→gold→API)로 분리되어 있어, 위 전환은 각각 한 모듈 교체로 끝납니다.

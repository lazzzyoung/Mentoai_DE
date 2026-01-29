# MentoAI: Personalized AI Career Roadmap Service

**MentoAI**는 사용자의 기술 스펙과 희망 직무를 분석하여, 최신 채용 공고 기반의 맞춤형 커리어 성장 로드맵을 제공하는 AI 서비스입니다. 데이터 엔지니어링 파이프라인(Kafka, Spark, Airflow)과 RAG(Retrieval-Augmented Generation) 기술을 결합하여, 단순한 공고 추천을 넘어 구체적인 학습 전략과 액션 플랜을 제시합니다.

## 🏗️ System Architecture

데이터의 수집부터 서비스 제공까지의 전체 데이터 흐름도입니다.

```text
[Data Ingestion Layer]             [Data Processing Layer]
+-----------------+               +--------------------------+
|  Job Sites      |   Crawling    |  Apache Spark (ETL)      |
| (Wanted, etc.)  | ------------> |                          |
+-----------------+               | 1. Ingest (Kafka->S3)    |-----> [AWS S3 (Bronze)]
         |                        | 2. Process (Clean Data)  |-----> [PostgreSQL (Silver)]
         v                        | 3. Upsert (Embedding)    |-----> [Qdrant (Gold)]
+-----------------+               +--------------------------+
|  Apache Kafka   |                            ^
| (career_raw)    |                            |
+-----------------+                 (Trigger / Schedule)
         |                                     |
         +---------------------------> +----------------+
                                       | Apache Airflow |
                                       +----------------+

[Service & AI Layer]
+--------+       +------------------+       +------------------+
|        | <---> |  FastAPI Server  | <---> |    Qdrant DB     |
|  User  |       |   (RAG Engine)   |       |  (Vector Search) |
|        |       +------------------+       +------------------+
+--------+                 ^
                           |
                 +------------------+
                 |   Google Gemini  |
                 |  (Reasoning/LLM) |
                 +------------------+


## 🚀 Key Features

1. **Automated Data Pipeline**
   - Apache Airflow와 Spark를 활용하여 채용 공고 데이터를 수집(Bronze), 정제(Silver), 벡터화(Gold)하는 ETL 파이프라인을 구축했습니다.
   - 초기 Streaming 아키텍처에서 안정적인 데이터 적재를 위해 Batch 방식으로 최적화되었습니다.

2. **Semantic Search (Vector Search)**
   - Qdrant 벡터 데이터베이스와 **KoSimCSE** 임베딩 모델을 사용하여, 단순 키워드 매칭이 아닌 문맥 기반의 직무 적합성 검색을 수행합니다.

3. **RAG Based Consulting**
   - **Google Gemini 3 Flash** 모델을 활용하여, 검색된 공고와 사용자 프로필을 비교 분석합니다.
   - 부족한 역량에 대한 점수화(Scoring) 및 구체적인 학습 로드맵(Gap Analysis)을 제공합니다.

## 🏗️ System Architecture (Medallion Architecture)

데이터는 Bronze, Silver, Gold 단계를 거치며 점진적으로 가공되어 서비스에 활용됩니다.

1. **Ingestion (Kafka)**: `producer_wanted.py`를 통해 공고 수집 후 `career_raw` 토픽으로 전송
2. **Bronze Layer (S3)**: 원본 JSON 데이터를 Parquet 형식으로 보존 (Data Lake)
3. **Silver Layer (PostgreSQL)**: Spark를 이용한 데이터 정제(HTML 제거, 스키마 검증) 및 RDBMS 적재
4. **Gold Layer (Qdrant)**: KoSimCSE 모델로 공고 본문 임베딩 후 벡터 DB 인덱싱
5. **Orchestration (Airflow)**: Docker-out-of-Docker 구조로 전체 파이프라인 스케줄링
6. **Service Layer (FastAPI)**: 사용자 요청 처리 및 RAG(Retrieval-Augmented Generation) 수행

## 📂 Project Structure

MENTOAI_DE/
├── dags/                       # Airflow DAG
│   └── mentoai_pipeline.py     # [Main] Kafka -> Bronze -> Silver -> Gold 통합 파이프라인
├── kafka/                      # 데이터 수집 모듈
│   ├── producer_wanted.py      # [Main] 실시간 공고 수집기
│   └── utils/
│       └── wanted_scraper.py   # 원티드 공고 크롤링 로직
├── spark/                      # 데이터 처리 모듈
│   ├── job_ingest_bronze.py    # Task 1: Kafka -> S3 (Parquet)
│   ├── job_process_silver.py   # Task 2: S3 -> Postgres (Data Cleaning)
│   ├── job_upsert_gold.py      # Task 3: Postgres -> Qdrant (Embedding)
│   └── utils/
│       ├── spark_session.py    # Spark 세션 생성 헬퍼
│       ├── text_cleaner.py     # 텍스트 전처리 유틸
│       └── writers.py          # DB/S3 적재 함수
├── server/                     # Backend API & AI Engine
│   ├── app/
│   │   └── main.py             # FastAPI 엔드포인트 & RAG 로직 (LangChain)
│   ├── Dockerfile
│   └── requirements.txt
├── infra/                      # 인프라 설정 (Docker)
│   ├── airflow/                # Airflow 빌드 설정
│   ├── spark/                  # Spark 빌드 설정
│   └── docker-compose.yml      # 전체 서비스 오케스트레이션
├── .env                        # 환경 변수 (AWS Key, Gemini Key, DB Info)
└── README.md                   # 본 문서

## 📡 API Endpoints

### 1. 기업 목록 추천
* **POST** `/api/v3/jobs/recommend/{user_id}`
* 사용자의 프로필(기술, 경력)과 가장 유사한 공고 5개를 추천하고, 적합도 점수를 반환합니다.

### 2. 상세 커리어 컨설팅
* **POST** `/api/v3/jobs/{job_id}/analyze/{user_id}`
* 특정 공고에 대해 합격을 위한 구체적인 전략(부족한 점, 액션 플랜, 면접 팁)을 JSON 형태로 제공합니다.

## ⚡ Prerequisites

이 프로젝트를 실행하기 위해 필요한 요구사항입니다.

* Docker & Docker Compose
* Python 3.9+
* API Keys:
    * Google Gemini API Key
    * AWS Access Key (S3 접근용)

---

## ⚡ Quick Start

### 1. 환경 설정 (Prerequisites)
프로젝트 루트에 `.env` 파일을 생성하고 필요한 API 키를 입력합니다.
(GOOGLE_API_KEY, AWS_ACCESS_KEY_ID, POSTGRES_USER, QDRANT_HOST 등)

### 2. 인프라 빌드 및 실행
각 서비스(Airflow, Spark, Server)를 개별 Dockerfile로 빌드하여 실행합니다.

cd infra
docker compose up -d --build

### 3. 데이터 파이프라인 실행
Airflow 웹 UI에 접속하여 파이프라인을 활성화합니다.
* **URL**: http://localhost:8081
* **Account**: admin / admin
* **Action**: `mentoai_pipeline` DAG를 Unpause(ON) 하고 Trigger 실행

### 4. API 서비스 사용
FastAPI Swagger UI를 통해 추천 및 컨설팅 API를 테스트할 수 있습니다.
* **URL**: http://localhost:8000/docs

## 🚀 Installation & Execution Guide

### 1. 환경 변수 설정
프로젝트 루트 디렉토리에 .env 파일을 생성하고 아래 내용을 채워주세요.

# .env 예시
GOOGLE_API_KEY=your_gemini_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
S3_BUCKET_NAME=mentoai-career-raw
DATABASE_URL=postgresql://airflow:airflow@postgres:5432/mentoai
QDRANT_HOST=mentoai-qdrant

### 2. 인프라 빌드 및 실행
infra 디렉토리로 이동하여 모든 서비스를 실행합니다.

cd infra
/ docker compose up -d --build

### 3. 데이터베이스 초기화 (User Data)
PostgreSQL 컨테이너에 접속하여 사용자 테이블을 생성하고 테스트 데이터를 입력합니다.

# Postgres 접속
/ docker exec -it mentoai-postgres psql -U airflow -d mentoai

# 테이블 생성 SQL 실행
/ CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

/ CREATE TABLE IF NOT EXISTS user_specs (
    spec_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    desired_job VARCHAR(100),
    career_years INT DEFAULT 0,
    education VARCHAR(100),
    skills TEXT[],
    certificates TEXT[],
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

# 테스트 데이터 입력
/ INSERT INTO users (username, email) VALUES ('강태영', 'tang0923@khu.ac.kr');

/ INSERT INTO user_specs (user_id, desired_job, career_years, education, skills, certificates) 
VALUES (1, 'Data Engineer', 0, '학사', ARRAY['Python', 'Spark', 'Kafka', 'Airflow'], ARRAY['정보처리기사', 'SQLD']);

# 입력 후 \q 로 종료

### 4. 데이터 파이프라인 실행 (Airflow)
1. 웹 브라우저에서 http://localhost:8081 접속
2. 로그인: admin / admin
3. mentoai_pipeline DAG를 찾아서 왼쪽의 Toggle을 ON으로 변경
4. 우측의 'Trigger DAG' 버튼 클릭
5. Graph View에서 Kafka -> Bronze -> Silver -> Gold 작업이 모두 Success로 변하는지 확인

### 5. API 테스트
파이프라인이 완료되면 RAG 서버가 준비됩니다. http://localhost:8000/docs 에 접속하거나 아래 명령어로 테스트하세요.

# 1. 기업 추천 목록 조회 (V3)
/ curl -X 'POST' 'http://localhost:8000/api/v3/jobs/recommend/1' -H 'accept: application/json' -d ''

# 2. 특정 기업 상세 컨설팅 (job_id는 위 응답에서 확인)
/ curl -X 'POST' 'http://localhost:8000/api/v3/jobs/{JOB_ID}/analyze/1' -H 'accept: application/json' -d ''

---

## 🛠️ Tech Stack Details

**Infrastructure**
* Docker Compose: 마이크로서비스(Airflow, Spark, DB, Server) 통합 관리

**Data Engineering**
* Kafka: 실시간 공고 데이터 버퍼링
* Spark (PySpark): 대용량 데이터 전처리 및 벡터화 (Batch Processing)
* Airflow: 데이터 파이프라인 의존성 관리 및 스케줄링

**Storage**
* PostgreSQL: 정형 데이터(사용자 정보, 정제된 공고) 저장
* Qdrant: 공고 텍스트 임베딩 벡터 저장 및 유사도 검색
* AWS S3: Raw Data(JSON/Parquet) 영구 보관 (Data Lake)

**AI & Backend**
* FastAPI: 비동기 API 서버
* LangChain: LLM 프롬프트 체이닝 및 Output Parsing
* Google Gemini 3 Flash: 추론 및 로드맵 생성
* KoSimCSE: 한국어 특화 문장 임베딩 모델

---

## ⚠️ Troubleshooting (Project History)

### 1. Airflow RBAC 권한 오류 (Access Denied)
* **현상**: DB 초기화 후 웹 UI 접속 시 'Admin' 역할이 없어 대시보드 접근 불가.
* **원인**: docker-compose down으로 인한 DB 휘발 및 자동 초기화 스크립트 재실행 실패.
* **해결**: 컨테이너 내부에서 `airflow users create` 명령어로 관리자 계정 수동 생성 및 권한 부여.

### 2. PostgreSQL 데이터 휘발 및 볼륨 이슈
* **현상**: 컨테이너를 내렸다 올리면 DB에 생성한 테이블과 유저 데이터가 사라짐.
* **원인**: Docker 볼륨 매핑 누락으로 데이터가 영구 저장되지 않음.
* **해결**: docker-compose.yml의 postgres 서비스에 `./postgres_data:/var/lib/postgresql/data` 매핑 추가.

### 3. Spark Streaming 적재 누락 (Fake Success)
* **현상**: Airflow 태스크는 성공으로 뜨지만 Postgres에 테이블이 생성되지 않음.
* **원인**: `writeStream` 사용 시 `awaitTermination()` 설정 부재로 적재 완료 전 세션 종료.
* **해결**: 유실 데이터 복구를 위해 S3 데이터를 몽땅 읽어 처리하는 **Batch Recovery 모드** 도입 및 테이블 강제 생성.

### 4. Qdrant 메타데이터 "미상" 출력 이슈
* **현상**: 추천 목록 API 응답에서 기업명과 공고명이 "미상"으로 나옴.
* **원인**: LangChain의 `vector_store`가 Qdrant의 특정 페이로드 필드를 읽어오지 못하는 호환성 문제.
* **해결**: Qdrant Raw Client를 사용하여 검색된 ID로 직접 포인트(Point)를 조회(`retrieve`)하여 페이로드를 확실하게 가져오도록 보정.

### 5. Gemini JSON Parsing 에러 (Output Parser)
* **현상**: V3 목록 조회 시 500 Internal Server Error 발생.
* **원인**: `JsonOutputParser`가 `List[JobSummary]` 형태를 직접 처리하지 못함.
* **해결**: 리스트를 감싸는 래퍼 클래스(`JobSummaryList`)를 정의하여 파서에게 전달함으로써 스키마 정합성 확보.

### 6. QdrantClient 버전 호환성 (search vs retrieve)
* **현상**: `client.search()` 호출 시 속성이 없다는 에러 발생.
* **원인**: 설치된 `qdrant-client` 라이브러리 버전이 낮아 최신 메서드 미지원.
* **해결**: 버전 의존성이 없는 `vector_store.similarity_search`로 ID를 먼저 찾고, 구버전에서도 지원하는 `client.retrieve`로 데이터를 가져오는 하이브리드 방식 적용.

### 7. 채점 인플레이션 (Scoring Calibration)
* **현상**: 사용자의 경력이 부족함에도 모든 공고에 90점 이상의 높은 점수가 부여됨.
* **원인**: 프롬프트의 채점 기준이 너무 관대함.
* **해결**: 프롬프트에 **"냉정한 IT 면접관"** 페르소나를 부여하고, 연차 미달 시 감점 조건을 명시하여 60~85점 사이의 현실적인 점수가 나오도록 조정.




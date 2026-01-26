# MentoAI: AI-Based Career Curation Pipeline

MentoAI는 채용 공고 데이터를 실시간으로 수집(Kafka), 정제(Spark), 벡터화(Qdrant)하여 사용자에게 최적의 커리어 로드맵과 채용 정보를 추천하는 RAG(Retrieval-Augmented Generation) 기반의 엔드투엔드 데이터 파이프라인입니다.

작성자: 강태영 (컴퓨터공학과 / 2022110200)
최종 수정일: 2026.01.26
기술 스택: Python, Apache Spark, Kafka, Airflow, PostgreSQL, Qdrant, Docker, AWS S3

## 시스템 아키텍처 (Medallion Architecture)

데이터는 Bronze, Silver, Gold 단계를 거치며 점진적으로 가공됩니다.

1. Ingestion (Kafka): producer_wanted.py를 통해 공고 수집 후 career_raw 토픽 전송
2. Bronze Layer (S3): 원본 JSON 데이터를 Parquet 형식으로 보존 (Data Lake)
3. Silver Layer (PostgreSQL): Spark를 이용한 데이터 정제(중복 제거, 결측치 처리) 및 RDBMS 적재
4. Gold Layer (Qdrant): KoSimCSE 모델로 공고 본문 임베딩 후 벡터 DB 인덱싱
5. Orchestration (Airflow): Docker-out-of-Docker 구조로 전체 파이프라인 스케줄링

## 프로젝트 구조

MENTOAI_DE/
├── dags/                   # Airflow DAG 정의
│   └── mentoai_pipeline.py # [Main] 전체 파이프라인 통합 DAG
├── kafka/                  # 데이터 수집 모듈
│   ├── producer_wanted.py  # [Main] 실시간 공고 수집기
│   └── utils/scraper.py    # 정규식 기반 크롤링 로직
├── spark/                  # 데이터 처리 모듈
│   ├── job_ingest_bronze.py # Task 1: Kafka -> S3
│   ├── job_process_silver.py# Task 2: S3 -> Postgres
│   └── job_upsert_gold.py   # Task 3: Postgres -> Qdrant
├── infra/                  # 인프라 설정 (Docker)
│   ├── airflow/            # Airflow 빌드 (Dockerfile, requirements.txt)
│   ├── spark/              # Spark 빌드 (Dockerfile, requirements.txt)
│   └── docker-compose.yml  # 서비스 통합 정의
├── .env                    # 환경 변수 (AWS Key, DB 정보 등)
└── README.md               # 본 문서

## 시작 가이드

### 1. 인프라 빌드 및 실행
각 서비스의 관심사를 분리하여 개별 Dockerfile로 관리합니다.

cd infra
docker compose up -d --build

### 2. 파이프라인 실행 및 접속
* Airflow UI: http://localhost:8081 (admin / admin)
* Spark Master: http://localhost:8082
* Qdrant Dashboard: http://localhost:6333/dashboard

## 주요 설정 및 트러블슈팅

### 관심사 분리 (Separation of Concerns)
* Airflow: 크롤링 및 스케줄링 위주 라이브러리 설치
* Spark: torch, sentence-transformers 등 무거운 AI 모델 라이브러리를 별도 빌드하여 이미지 최적화

### Docker-out-of-Docker 권한 해결
Airflow 컨테이너에서 호스트의 Docker 소켓에 접근하기 위한 권한 설정이 필요할 수 있습니다.

docker exec -u 0 -it airflow-scheduler chmod 666 /var/run/docker.sock

### 임베딩 모델 정보
* Model: BM-K/KoSimCSE-roberta-multitask
* Dimension: 768
* Strategy: Mean Pooling (Sentence-transformers 자동 변환 적용)

### 데이터 재처리 (Backfill)
S3의 체크포인트를 삭제하면 데이터를 처음부터 다시 처리할 수 있습니다.

aws s3 rm s3://mentoai-career-raw/silver/checkpoints/ --recursive
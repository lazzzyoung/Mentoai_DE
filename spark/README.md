⚡ MentoAI: AI-Based Career Data Pipeline
채용 공고 데이터를 수집(Kafka), 저장(S3), 정제(PostgreSQL), 그리고 벡터화(Qdrant)하여 사용자 맞춤형 커리어 큐레이션을 제공하는 엔드투엔드 데이터 파이프라인입니다.

작성자: 강태영 (컴퓨터공학과 / 2022110200)

기술 스택: Python, Apache Spark, Kafka, Airflow, PostgreSQL, Qdrant, AWS S3

📂 프로젝트 구조
Plaintext
MENTOAI-DE/
├── kafka/              # 데이터 수집 모듈 (Producer)
├── spark/              # 데이터 처리 모듈 (Medallion Architecture)
│   ├── utils/          # Spark Session, Reader/Writer, Cleaner
│   ├── job_ingest_bronze.py  # Job 1: Kafka -> S3
│   ├── job_process_silver.py # Job 2: S3 -> Postgres
│   └── job_upsert_gold.py    # Job 3: Postgres -> Qdrant (예정)
├── infra/              # Docker Compose 및 인프라 설정
├── .env                # 환경 변수 (AWS Key, DB 접속 정보 등)
└── requirements.txt    # 통합 파이썬 라이브러리 설정
🚀 시작 가이드
1. Spark 컨테이너 접속 및 환경 설정
Docker Compose가 실행 중인 상태에서 Spark Master 컨테이너에 접속하여 의존성 라이브러리를 설치합니다.

Bash
# 1. Spark Master 컨테이너 접속
docker exec -it spark-master bash

# 2. 컨테이너 내부에서 통합 requirements.txt 설치
# (볼륨 마운트 설정에 따라 /opt/airflow 경로에 위치함)
pip install -r /opt/airflow/requirements.txt
2. 파이프라인 실행 프로세스
모든 Spark Job은 spark-master 컨테이너 내부의 /opt/airflow/spark 경로에서 spark-submit으로 실행합니다.

## Step 1: Bronze Layer (Raw 데이터 적재)
Kafka의 데이터를 S3에 원본 그대로 저장합니다.

Bash
/opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
  /opt/airflow/spark/job_ingest_bronze.py

## Step 2: Silver Layer (데이터 정제 및 RDBMS 적재)
S3의 데이터를 읽어 구조화한 뒤 PostgreSQL에 저장합니다.

Bash
/opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262,org.postgresql:postgresql:42.6.0 \
  job_process_silver.py

## Step 3: Gold Layer (임베딩 및 인덱싱, Vector DB 적재)
Postgres DB의 데이터를 읽어 Embedding & Indexing 후 Vector DB(Qdrant) 에 적재합니다.

Bash
/opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.postgresql:postgresql:42.6.0 \
  job_upsert_gold.py

🛠 주요 처리 로직
중복 제거: id 필드를 기준으로 dropDuplicates를 수행하여 데이터 일관성을 유지합니다.

결측치 처리: 마감일(due_time) 정보가 없는 경우 "상시채용"으로 기본값을 할당합니다.

유니코드 복구: JSON 파싱 과정에서 이스케이프된 한글 텍스트를 원래 문자로 복원합니다.

체크포인트 관리: 데이터 유실 및 중복 처리를 방지하기 위해 S3 내에 전용 checkpoints/ 경로를 운영합니다.

⚠️ 주의 사항
S3 체크포인트 초기화: 로직(스키마)이 변경된 경우, 반드시 S3의 checkpoints/ 폴더를 삭제한 후 재실행해야 합니다.

DB 스키마: 새로운 필드(location, is_newbie 등) 추가 시 PostgreSQL에 해당 컬럼이 생성되어 있는지 확인하십시오.

네트워크: Docker 컨테이너 간 통신 시 localhost가 아닌 서비스 이름(kafka, postgres, qdrant)을 사용해야 합니다.
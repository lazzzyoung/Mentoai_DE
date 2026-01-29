import os
from datetime import datetime, timedelta
import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

# 한국 시간 설정
local_tz = pendulum.timezone("Asia/Seoul")

# 공통 설정
default_args = {
    'owner': 'mentoai',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 26, tzinfo=local_tz),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='mentoai_pipeline',
    default_args=default_args,
    description='End-to-End Career Data Pipeline (Batch Flow)',
    schedule_interval='0 9,16 * * *', # 매일 09:00, 16:00 정기 실행
    catchup=False,
    tags=['career', 'etl', 'spark', 'vector_db'],
) as dag:

    # 원본 데이터 수집 (Kafka)
    t1_producer = BashOperator(
        task_id='run_kafka_producer',
        bash_command='python3 /opt/airflow/kafka/producer_wanted.py',
    )

    # Bronze: Kafka -> S3 (Batch/Streaming)
    t2_bronze = BashOperator(
        task_id='spark_ingest_bronze',
        bash_command="""
        docker exec spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
        /opt/airflow/spark/job_ingest_bronze.py
        """
    )

    # Silver: S3 -> Postgres (Batch)
    t3_silver = BashOperator(
        task_id='spark_process_silver',
        bash_command="""
        docker exec spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262,org.postgresql:postgresql:42.6.0 \
        /opt/airflow/spark/job_process_silver.py
        """
    )

    # Gold: Postgres -> Qdrant (Vector DB 적재)
    t4_gold = BashOperator(
        task_id='spark_upsert_gold',
        bash_command="""
        docker exec spark-master /opt/spark/bin/spark-submit \
        --master spark://spark-master:7077 \
        --packages org.postgresql:postgresql:42.6.0 \
        /opt/airflow/spark/job_upsert_gold.py
        """
    )

    t1_producer >> t2_bronze >> t3_silver >> t4_gold
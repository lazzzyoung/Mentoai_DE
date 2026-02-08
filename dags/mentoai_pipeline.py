from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

KST = pendulum.timezone("Asia/Seoul")
SPARK_MASTER_URL = "spark://spark-master:7077"
SPARK_SUBMIT = (
    f"docker exec spark-master /opt/spark/bin/spark-submit --master {SPARK_MASTER_URL}"
)

DEFAULT_ARGS = {
    "owner": "mentoai",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="mentoai_pipeline",
    default_args=DEFAULT_ARGS,
    description="End-to-End Career Data Pipeline (Batch Flow)",
    start_date=pendulum.datetime(2026, 1, 26, tz=KST),
    schedule="0 9,16 * * *",
    catchup=False,
    tags=["career", "etl", "spark", "vector_db"],
) as dag:
    t1_producer = BashOperator(
        task_id="run_kafka_producer",
        bash_command="python3 /opt/airflow/kafka/producer_wanted.py",
    )

    t2_bronze = BashOperator(
        task_id="spark_ingest_bronze",
        bash_command=(
            f"{SPARK_SUBMIT} "
            "--packages "
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "com.amazonaws:aws-java-sdk-bundle:1.12.262 "
            "/opt/airflow/spark/job_ingest_bronze.py"
        ),
    )

    t3_silver = BashOperator(
        task_id="spark_process_silver",
        bash_command=(
            f"{SPARK_SUBMIT} "
            "--packages "
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "com.amazonaws:aws-java-sdk-bundle:1.12.262,"
            "org.postgresql:postgresql:42.6.0 "
            "/opt/airflow/spark/job_process_silver.py"
        ),
    )

    t4_gold = BashOperator(
        task_id="spark_upsert_gold",
        bash_command=(
            f"{SPARK_SUBMIT} "
            "--packages org.postgresql:postgresql:42.6.0 "
            "/opt/airflow/spark/job_upsert_gold.py"
        ),
    )

    t1_producer >> t2_bronze >> t3_silver >> t4_gold

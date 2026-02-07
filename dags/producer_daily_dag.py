from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

KST = pendulum.timezone("Asia/Seoul")

DEFAULT_ARGS = {
    "owner": "mentoai",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="producer_daily_dag",
    default_args=DEFAULT_ARGS,
    description="매일 최신 채용 공고를 수집하여 Kafka로 전송",
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    schedule="0 9 * * *",
    catchup=False,
    tags=["ingestion", "kafka", "work24"],
) as dag:
    run_producer = BashOperator(
        task_id="run_daily_producer",
        bash_command=(
            "export KAFKA_BOOTSTRAP_SERVERS='kafka:29092' && "
            "export PYTHONPATH=$PYTHONPATH:/opt/airflow && "
            "python3 /opt/airflow/kafka/producer_recruit24_daily.py"
        ),
    )

    run_producer

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
    dag_id="producer_backfill_dag",
    default_args=DEFAULT_ARGS,
    description="과거 채용 공고를 페이지 범위로 수집하여 Kafka에 전송",
    start_date=pendulum.datetime(2026, 1, 1, tz=KST),
    schedule=None,
    catchup=False,
    tags=["backfill", "kafka", "work24"],
) as dag:
    backfill_task = BashOperator(
        task_id="run_backfill_producer",
        bash_command=(
            "export KAFKA_BOOTSTRAP_SERVERS='kafka:29092' && "
            "export KAFKA_TOPIC_NAME='career_raw' && "
            "export PYTHONPATH=$PYTHONPATH:/opt/airflow && "
            "python3 /opt/airflow/kafka/producer_recruit24_backfill.py "
            "{{ dag_run.conf.get('start_page', 1) }} "
            "{{ dag_run.conf.get('end_page', 2) }}"
        ),
    )

    backfill_task

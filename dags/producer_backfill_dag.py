from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime

default_args = {
    'owner': 'taeyeong',
    'start_date': datetime(2026, 1, 1),
}

with DAG(
    'producer_backfill_dag', 
    default_args=default_args,
    schedule_interval=None, 
    catchup=False,
    tags=['backfill', 'kafka']
) as dag:

    backfill_task = BashOperator(
        task_id='run_backfill_producer',
        bash_command="""
            # 1. 라이브러리 설치
            pip install kafka-python requests beautifulsoup4

            # 2. 환경변수 및 경로 설정
            export KAFKA_BOOTSTRAP_SERVERS='kafka:29092'
            export PYTHONPATH=$PYTHONPATH:/opt/airflow

            # 3. 실행 (인자값 전달)
            python3 /opt/airflow/kafka/producer_backfill.py \
            {{ dag_run.conf.get('start_page', 1) }} \
            {{ dag_run.conf.get('end_page', 2) }}
        """
    )

    backfill_task
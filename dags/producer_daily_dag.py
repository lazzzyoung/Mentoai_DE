from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'taeyeong',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'producer_daily_dag', 
    default_args=default_args,
    description='매일 최신 채용 공고를 수집하여 Kafka로 전송',
    schedule_interval='0 9 * * *',
    catchup=False,
    tags=['ingestion', 'kafka', 'work24']
) as dag:

    run_producer = BashOperator(
        task_id='run_daily_producer',
        bash_command="""
            # 1. 라이브러리 설치
            pip install kafka-python requests beautifulsoup4

            # 2. 환경변수 및 경로 설정
            export KAFKA_BOOTSTRAP_SERVERS='kafka:29092'
            export PYTHONPATH=$PYTHONPATH:/opt/airflow

            # 3. 실행
            python3 /opt/airflow/kafka/producer_daily.py
        """
    )

    run_producer
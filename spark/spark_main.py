import os
import sys
from dotenv import load_dotenv

# utils 임포트용 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.spark_session import create_spark_session
from spark.utils.readers import read_from_kafka
from utils.text_cleaner import clean_job_details
from spark.utils.writers import write_to_s3, write_to_postgres

load_dotenv() 

def run_spark_job():
    print("🚀 Spark Job Started: Ingestion & Processing")

    # 1. Spark 세션 생성
    spark = create_spark_session("MentoAI_Main_Pipeline")

    # 2. Kafka로부터 데이터 읽기
    raw_df = read_from_kafka(spark)

    # 3. 데이터 파싱 및 정제 (JSON -> Schema -> Clean)
    refined_df = clean_job_details(raw_df)
    
    # 디버깅용: 스키마 출력
    refined_df.printSchema()

    # 4. 결과 저장 (Multi-Sink: S3 & Postgres)
    query_s3 = write_to_s3(refined_df)
    # query_db = write_to_postgres(refined_df)
    
    # 5. 스트리밍 종료 대기
    query_s3.awaitTermination()
    # query_db.awaitTermination()
    
    print("✅ All Streaming Jobs Completed!")

if __name__ == "__main__":
    run_spark_job()
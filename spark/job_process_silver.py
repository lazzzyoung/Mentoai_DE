import sys
import os
from dotenv import load_dotenv
from pyspark.sql.functions import col

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utils.spark_session import create_spark_session
from utils.text_cleaner import clean_job_details
from utils.writers import write_to_postgres

load_dotenv()

def run_process_silver():
    spark = create_spark_session("MentoAI_Job2_Silver")
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    
    bronze_path = f"s3a://{bucket_name}/bronze/career_raw/"
    
    print(f"📂 Reading from S3 Bronze: {bronze_path}")

    # S3 Bronze 데이터 읽기
    try:
        bronze_schema = spark.read.parquet(bronze_path).schema
    except Exception as e:
        print("⚠️ Bronze 데이터 경로가 없거나 비어있습니다. 먼저 job_ingest_bronze.py를 실행해주세요.")
        return

    # Streaming DataFrame 생성
    raw_file_df = spark.readStream \
        .format("parquet") \
        .schema(bronze_schema) \
        .option("maxFilesPerTrigger", 100) \
        .load(bronze_path)
    
    # Bronze의 'raw_json' 컬럼을 'value'로 변경하여 패스
    input_df = raw_file_df.withColumnRenamed("raw_json", "value")
    
    # 파싱 및 정제
    refined_df = clean_job_details(input_df)
    
    # PostgreSQL Silver에 저장
    query = write_to_postgres(refined_df)
    
    print("⏳ Silver Layer(Postgres) 적재 중...")
    query.awaitTermination()

if __name__ == "__main__":
    run_process_silver()
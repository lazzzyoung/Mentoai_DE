import sys
import os
from dotenv import load_dotenv
from pyspark.sql.functions import col

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utils.spark_session import create_spark_session
from utils.text_cleaner import clean_job_details


load_dotenv()

def run_recovery_silver():
    # 세션 생성
    spark = create_spark_session("MentoAI_Job2_Silver_Recovery")
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    bronze_path = f"s3a://{bucket_name}/bronze/career_raw/"
    
    print(f"📂 Reading ALL data from S3 Bronze (Batch Mode): {bronze_path}")

    # read (Batch)
    try:
        
        raw_df = spark.read.parquet(bronze_path)
    except Exception as e:
        print(f"⚠️ 에러 발생: {e}")
        return

    # 데이터 정제
    input_df = raw_df.withColumnRenamed("raw_json", "value")
    refined_df = clean_job_details(input_df)
    
    count = refined_df.count()
    print(f" 정제된 데이터 개수: {count}건")

    if count > 0:
        # PostgreSQL에 직접 쓰기 (Batch)
        db_url = os.getenv("DB_URL", "jdbc:postgresql://postgres:5432/mentoai")
        print("💾 Saving to Postgres...")
        
        refined_df.write \
            .format("jdbc") \
            .option("url", db_url) \
            .option("dbtable", "career_jobs") \
            .option("user", "airflow") \
            .option("password", "airflow") \
            .option("driver", "org.postgresql.Driver") \
            .mode("overwrite") \
            .save()
        
        print("🎉 career_jobs 테이블 생성 및 데이터 적재 완료!")
    else:
        print(" 적재할 데이터가 없습니다.")

    spark.stop()

if __name__ == "__main__":
    run_recovery_silver()
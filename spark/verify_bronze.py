import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utils.spark_session import create_spark_session
from utils.readers import read_stream_from_kafka
from utils.writers import write_raw_to_s3 

load_dotenv()


def verify_bronze_data():
    spark = create_spark_session("Verify_Bronze_Data")
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    # Bronze 데이터 경로
    bronze_path = f"s3a://{bucket_name}/bronze/career_raw/"

    print(f"🔍 S3 경로 확인: {bronze_path}")

    try:
        
        df = spark.read.parquet(bronze_path)
        
        count = df.count()
        print(f"📊 총 저장된 데이터 개수: {count}건")
        
        if count > 0:
            print("\n📋 [샘플 데이터 Top 3]")
            df.selectExpr(
                "collected_date", 
                "raw_json as json_preview", 
                "ingestion_time"
            ).show(3, truncate=False)
        else:
            print("⚠️ 데이터가 없습니다. Producer를 실행했는지 확인해주세요.")
            
    except Exception as e:
        print(f"❌ 읽기 실패 (경로가 없거나 권한 문제일 수 있음): {e}")

if __name__ == "__main__":
    verify_bronze_data()
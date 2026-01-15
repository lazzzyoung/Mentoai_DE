import os
from dotenv import load_dotenv
from pyspark.sql import SparkSession

load_dotenv()

spark = SparkSession.builder \
    .appName("Verify_S3") \
    .config("spark.jars.packages", "org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262") \
    .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID")) \
    .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY")) \
    .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
    .config("spark.hadoop.fs.s3a.endpoint", f"s3.{os.getenv('AWS_REGION')}.amazonaws.com") \
    .getOrCreate()

bucket = os.getenv("S3_BUCKET_NAME")
print(f"🔍 S3 ({bucket}) 데이터 읽기 시도...")

try:
    df = spark.read.parquet(f"s3a://{bucket}/raw/")
    df.show(truncate=False)
    print(f"✅ 총 {df.count()}건의 데이터를 확인했습니다.")
except Exception as e:
    print(f"❌ 읽기 실패: {e}")

spark.stop()
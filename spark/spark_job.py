import os
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col
from pyspark.sql.types import StructType, StructField, StringType

load_dotenv()

def create_spark_session():

    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION", "ap-northeast-2")

    if not aws_access_key or not aws_secret_key:
        raise ValueError("❌ .env 파일에 AWS Access Key가 없습니다!")

    # Spark 세션 생성 (AWS S3 패키지 포함)
    spark = SparkSession.builder \
        .appName("MentoAI_Career_Ingestion") \
        .master("local[*]") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.access.key", aws_access_key) \
        .config("spark.hadoop.fs.s3a.secret.key", aws_secret_key) \
        .config("spark.hadoop.fs.s3a.endpoint", f"s3.{aws_region}.amazonaws.com") \
        .getOrCreate()
    return spark

def run_spark_job():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    bucket_name = os.getenv("S3_BUCKET_NAME")
    print(f"🚀 Spark Streaming 시작: Kafka -> AWS S3 ({bucket_name})")

    kafka_df = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("subscribe", "career_raw") \
        .option("startingOffsets", "earliest") \
        .load()

    # JSON 데이터 스키마 정의 
    schema = StructType([
        StructField("source_id", StringType()),
        StructField("company", StringType()),
        StructField("title", StringType()),
        StructField("link", StringType()),
        StructField("pay", StringType()),
        StructField("location", StringType()),
        StructField("deadline", StringType()),
        StructField("reg_date", StringType()),
        StructField("description", StringType()),
        StructField("requirements", StringType()),
        StructField("preferred_qualifications", StringType()),
        StructField("collected_at", StringType())
    ])

    # 데이터 파싱
    processed_df = kafka_df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*")

    # S3에 저장 (Parquet 포맷)
    # path: 실제 데이터가 저장될 경로
    # checkpointLocation: 스트리밍 상태 저장
    query = processed_df.writeStream \
        .format("parquet") \
        .outputMode("append") \
        .option("path", f"s3a://{bucket_name}/raw/") \
        .option("checkpointLocation", f"s3a://{bucket_name}/checkpoints/") \
        .start()

    print("⏳ AWS S3로 데이터 적재 중... (Ctrl+C로 종료)")
    query.awaitTermination()

if __name__ == "__main__":
    run_spark_job()
import os
from pyspark.sql import SparkSession

def create_spark_session(app_name):
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
    aws_region = os.getenv("AWS_REGION", "ap-northeast-2")
    s3_endpoint_url = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
    s3_use_ssl = os.getenv("S3_USE_SSL", "false")
    s3_path_style_access = os.getenv("S3_PATH_STYLE_ACCESS", "true")

    packages = [
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
        "org.postgresql:postgresql:42.6.0" 
    ]

    spark = SparkSession.builder \
        .appName(app_name) \
        .master("local[*]") \
        .config("spark.jars.packages", ",".join(packages)) \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.access.key", aws_access_key) \
        .config("spark.hadoop.fs.s3a.secret.key", aws_secret_key) \
        .config("spark.hadoop.fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider") \
        .config("spark.hadoop.fs.s3a.path.style.access", s3_path_style_access) \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", s3_use_ssl) \
        .config("spark.hadoop.fs.s3a.endpoint", s3_endpoint_url or f"s3.{aws_region}.amazonaws.com") \
        .getOrCreate()
        
    spark.sparkContext.setLogLevel("WARN")
    return spark

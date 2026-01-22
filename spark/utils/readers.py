import os
from pyspark.sql import DataFrame

# Kafka로부터 실시간 스트리밍 데이터를 읽어옵니다.
def read_stream_from_kafka(spark, bootstrap_servers, topic_name, starting_offsets="earliest"):
    """
    [Job 1용] Kafka로부터 실시간 스트리밍 데이터를 읽어옵니다.
    """
    print(f"📡 Kafka Read Stream 초기화: {bootstrap_servers} | Topic: {topic_name}")
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", bootstrap_servers) \
        .option("subscribe", topic_name) \
        .option("startingOffsets", starting_offsets) \
        .option("failOnDataLoss", "false") \
        .load()

# S3 Bronze Layer(Parquet)에 새로 추가되는 파일을 감시하며 읽어옵니다.
def read_stream_from_s3(spark, bucket_name, source_path):
    
    full_path = f"s3a://{bucket_name}/{source_path}"
    print(f"📂 S3 Stream Read 시작: {full_path}")
    
    # 저장된 Parquet 파일에서 스키마를 샘플링.
    try:
        sample_schema = spark.read.parquet(full_path).schema
    except Exception:
        # 데이터가 아예 없을 경우를 대비한 기본 스키마 (최초 실행 시 필요)
        from pyspark.sql.types import StructType, StructField, StringType
        sample_schema = StructType([StructField("raw_json", StringType())])

    return spark.readStream \
        .format("parquet") \
        .schema(sample_schema) \
        .option("maxFilesPerTrigger", 100) \
        .load(full_path)
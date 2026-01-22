import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from utils.spark_session import create_spark_session
from utils.readers import read_stream_from_kafka
from utils.writers import write_raw_to_s3 

load_dotenv()

kafka_bootstrap = os.getenv('KAFKA_BOOTSTRAP_SERVERS')
topic_name = os.getenv('KAFKA_TOPIC_NAME')

def run_ingest_bronze():
    spark = create_spark_session("MentoAI_Job1_Bronze")
    
    # Kafka에서 Raw Data 읽기
    raw_kafka_df = read_stream_from_kafka(spark, kafka_bootstrap, topic_name)
    
    # metadata 추가
    from pyspark.sql.functions import col, get_json_object, to_date, current_timestamp
    
    bronze_df = raw_kafka_df.selectExpr("CAST(value AS STRING) as raw_json") \
        .withColumn("collected_at", get_json_object(col("raw_json"), "$.collected_at")) \
        .withColumn("collected_date", to_date(col("collected_at"))) \
        .withColumn("ingestion_time", current_timestamp())

    # S3 Bronze 경로에 저장
    query = write_raw_to_s3(bronze_df)
    query.awaitTermination()

if __name__ == "__main__":
    run_ingest_bronze()
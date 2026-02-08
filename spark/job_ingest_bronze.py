import logging

from dotenv import load_dotenv
from pyspark.sql.functions import col, current_timestamp, get_json_object, to_date

from utils.config import load_runtime_config
from utils.readers import read_stream_from_kafka
from utils.spark_session import create_spark_session
from utils.writers import write_raw_to_s3

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_ingest_bronze() -> None:
    runtime_config = load_runtime_config()
    if not runtime_config.s3_bucket_name:
        raise ValueError("S3_BUCKET_NAME 환경변수가 필요합니다.")

    spark = create_spark_session("MentoAI_Job1_Bronze", runtime_config)

    raw_kafka_df = read_stream_from_kafka(
        spark=spark,
        bootstrap_servers=runtime_config.kafka_bootstrap_servers,
        topic_name=runtime_config.kafka_topic_name,
    )

    bronze_df = (
        raw_kafka_df.selectExpr("CAST(value AS STRING) as raw_json")
        .withColumn("collected_at", get_json_object(col("raw_json"), "$.collected_at"))
        .withColumn("collected_date", to_date(col("collected_at")))
        .withColumn("ingestion_time", current_timestamp())
    )

    query = write_raw_to_s3(bronze_df, runtime_config.s3_bucket_name)
    logger.info("Bronze 적재 query 시작")
    query.awaitTermination()


if __name__ == "__main__":
    run_ingest_bronze()

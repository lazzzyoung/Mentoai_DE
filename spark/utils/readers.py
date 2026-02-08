import logging

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StringType, StructField, StructType

logger = logging.getLogger(__name__)


def read_stream_from_kafka(
    spark: SparkSession,
    bootstrap_servers: str,
    topic_name: str,
    starting_offsets: str = "earliest",
) -> DataFrame:
    logger.info(
        "Kafka Read Stream 초기화: bootstrap=%s topic=%s", bootstrap_servers, topic_name
    )
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap_servers)
        .option("subscribe", topic_name)
        .option("startingOffsets", starting_offsets)
        .option("failOnDataLoss", "false")
        .load()
    )


def read_stream_from_s3(
    spark: SparkSession, bucket_name: str, source_path: str
) -> DataFrame:
    full_path = f"s3a://{bucket_name}/{source_path}"
    logger.info("S3 Stream Read 시작: %s", full_path)

    try:
        sample_schema = spark.read.parquet(full_path).schema
    except Exception:
        sample_schema = StructType([StructField("raw_json", StringType())])

    return (
        spark.readStream.format("parquet")
        .schema(sample_schema)
        .option("maxFilesPerTrigger", 100)
        .load(full_path)
    )

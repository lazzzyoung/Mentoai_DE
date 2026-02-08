import logging

from pyspark.sql import DataFrame

logger = logging.getLogger(__name__)


def write_raw_to_s3(df: DataFrame, bucket_name: str):
    s3_path = f"s3a://{bucket_name}/bronze/career_raw/"
    checkpoint_path = f"s3a://{bucket_name}/bronze/checkpoints/career_raw/"

    logger.info("Raw 데이터를 S3에 저장합니다: %s", s3_path)

    return (
        df.writeStream.format("parquet")
        .outputMode("append")
        .partitionBy("collected_date")
        .option("path", s3_path)
        .option("checkpointLocation", checkpoint_path)
        .trigger(availableNow=True)
        .start()
    )


def write_batch_to_postgres(
    df: DataFrame,
    db_url: str,
    db_user: str,
    db_password: str,
    db_table: str = "career_jobs",
    mode: str = "append",
) -> None:
    record_count = df.count()
    if record_count == 0:
        logger.info("Postgres 적재할 데이터가 없습니다.")
        return

    df.write.format("jdbc").option("url", db_url).option("dbtable", db_table).option(
        "user", db_user
    ).option("password", db_password).option("driver", "org.postgresql.Driver").mode(
        mode
    ).save()

    logger.info(
        "Postgres 적재 완료: table=%s count=%s mode=%s", db_table, record_count, mode
    )

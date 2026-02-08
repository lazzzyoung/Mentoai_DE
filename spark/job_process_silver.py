import logging

from dotenv import load_dotenv
from pyspark.sql.functions import col

from utils.config import load_runtime_config
from utils.spark_session import create_spark_session
from utils.text_cleaner import clean_job_details
from utils.writers import write_batch_to_postgres

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _jdbc_properties(db_user: str, db_password: str) -> dict[str, str]:
    return {"user": db_user, "password": db_password, "driver": "org.postgresql.Driver"}


def _is_missing_career_jobs_table_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "career_jobs" in message and (
        "does not exist" in message
        or "table or view not found" in message
        or "undefinedtable" in message
    )


def run_recovery_silver() -> None:
    runtime_config = load_runtime_config()
    if not runtime_config.s3_bucket_name:
        raise ValueError("S3_BUCKET_NAME 환경변수가 필요합니다.")

    spark = create_spark_session("MentoAI_Job2_Silver_Recovery", runtime_config)

    bronze_path = f"s3a://{runtime_config.s3_bucket_name}/bronze/career_raw/"
    logger.info("Bronze 데이터를 읽습니다: %s", bronze_path)

    try:
        raw_df = spark.read.parquet(bronze_path)
    except Exception as exc:
        logger.error("Bronze 데이터 로드 실패: %s", exc)
        spark.stop()
        return

    input_df = raw_df.withColumnRenamed("raw_json", "value")
    refined_df = clean_job_details(input_df)
    incremental_df = refined_df

    try:
        existing_ids_df = spark.read.jdbc(
            url=runtime_config.db_url,
            table="career_jobs",
            properties=_jdbc_properties(
                runtime_config.db_user,
                runtime_config.db_password,
            ),
        ).select(col("id").alias("existing_id"))
        incremental_df = refined_df.join(
            existing_ids_df,
            refined_df.id == existing_ids_df.existing_id,
            "left_anti",
        )
    except Exception as exc:
        if _is_missing_career_jobs_table_error(exc):
            logger.info("기존 career_jobs 테이블이 없어 전체를 append합니다.")
        else:
            logger.exception("기존 career_jobs 로드 실패로 작업을 중단합니다.")
            spark.stop()
            raise

    write_batch_to_postgres(
        df=incremental_df,
        db_url=runtime_config.db_url,
        db_user=runtime_config.db_user,
        db_password=runtime_config.db_password,
        db_table="career_jobs",
        mode="append",
    )

    spark.stop()


if __name__ == "__main__":
    run_recovery_silver()

import logging

from dotenv import load_dotenv

from utils.config import load_runtime_config
from utils.spark_session import create_spark_session
from utils.text_cleaner import clean_job_details
from utils.writers import write_batch_to_postgres

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

    record_count = refined_df.count()
    logger.info("정제된 데이터 개수: %s", record_count)

    write_batch_to_postgres(
        df=refined_df,
        db_url=runtime_config.db_url,
        db_user=runtime_config.db_user,
        db_password=runtime_config.db_password,
        db_table="career_jobs",
        mode="overwrite",
    )

    spark.stop()


if __name__ == "__main__":
    run_recovery_silver()

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SparkRuntimeConfig:
    kafka_bootstrap_servers: str
    kafka_topic_name: str
    s3_bucket_name: str
    db_url: str
    db_user: str
    db_password: str
    aws_access_key_id: str | None
    aws_secret_access_key: str | None
    aws_region: str
    qdrant_host: str
    qdrant_port: int
    qdrant_collection: str


def load_runtime_config() -> SparkRuntimeConfig:
    return SparkRuntimeConfig(
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        kafka_topic_name=os.getenv("KAFKA_TOPIC_NAME", "career_raw"),
        s3_bucket_name=os.getenv("S3_BUCKET_NAME", ""),
        db_url=os.getenv("DB_URL", "jdbc:postgresql://postgres:5432/mentoai"),
        db_user=os.getenv("DB_USER", "airflow"),
        db_password=os.getenv("DB_PASSWORD", "airflow"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_region=os.getenv("AWS_REGION", "ap-northeast-2"),
        qdrant_host=os.getenv("QDRANT_HOST", "mentoai-qdrant"),
        qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
        qdrant_collection=os.getenv("QDRANT_COLLECTION_NAME", "career_jobs"),
    )

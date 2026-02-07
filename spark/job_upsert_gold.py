import logging
from typing import TYPE_CHECKING, Any, cast

from dotenv import load_dotenv
from pyspark.sql.functions import coalesce, col, lit
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

from utils.config import SparkRuntimeConfig, load_runtime_config
from utils.spark_session import create_spark_session

if TYPE_CHECKING:
    from pyspark.core.rdd import RDD

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VECTOR_SIZE = 768
EMBEDDING_MODEL_NAME = "BM-K/KoSimCSE-roberta-multitask"


def get_postgres_properties(runtime_config: SparkRuntimeConfig) -> dict[str, str]:
    return {
        "user": runtime_config.db_user,
        "password": runtime_config.db_password,
        "driver": "org.postgresql.Driver",
    }


def init_qdrant_collection(runtime_config: SparkRuntimeConfig) -> None:
    client = QdrantClient(
        host=runtime_config.qdrant_host, port=runtime_config.qdrant_port
    )
    if client.collection_exists(collection_name=runtime_config.qdrant_collection):
        return

    client.create_collection(
        collection_name=runtime_config.qdrant_collection,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE, distance=models.Distance.COSINE
        ),
    )
    logger.info("Qdrant 컬렉션 생성 완료: %s", runtime_config.qdrant_collection)


def _build_context_text(row) -> str:
    skills_str = ", ".join(row.skill_tags) if row.skill_tags else "없음"
    return (
        f"[회사] {row.company}\n"
        f"[포지션] {row.position}\n"
        f"[경력요건] {row.annual_from}년 ~ {row.annual_to}년\n"
        f"[기술스택] {skills_str}\n"
        f"[주요업무] {row.main_tasks}\n"
        f"[자격요건] {row.requirements}\n"
        f"[우대사항] {row.preferred_points}"
    )


def process_partition(iterator, runtime_config: SparkRuntimeConfig):
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    client = QdrantClient(
        host=runtime_config.qdrant_host, port=runtime_config.qdrant_port
    )

    points = []
    for row in iterator:
        context_text = _build_context_text(row)
        embedding_vector = model.encode(context_text).tolist()

        payload = {
            "id": row.id,
            "company": row.company,
            "position": row.position,
            "is_newbie": row.is_newbie,
            "annual_from": row.annual_from,
            "annual_to": row.annual_to,
            "skills": ", ".join(row.skill_tags) if row.skill_tags else "없음",
            "intro": row.intro,
            "hire_rounds": row.hire_rounds,
            "full_text": context_text,
        }

        points.append(
            models.PointStruct(id=row.id, vector=embedding_vector, payload=payload)
        )

    if points:
        client.upsert(collection_name=runtime_config.qdrant_collection, points=points)

    yield len(points)


def run_upsert_gold() -> None:
    runtime_config = load_runtime_config()
    spark = create_spark_session("MentoAI_Job3_Gold", runtime_config)

    logger.info("Postgres Silver Layer에서 데이터를 읽습니다.")
    silver_df = spark.read.jdbc(
        url=runtime_config.db_url,
        table="career_jobs",
        properties=get_postgres_properties(runtime_config),
    )

    target_df = silver_df.select(
        col("id"),
        col("company"),
        col("position"),
        col("is_newbie"),
        col("annual_from"),
        col("annual_to"),
        col("skill_tags"),
        coalesce(col("intro"), lit("")).alias("intro"),
        coalesce(col("hire_rounds"), lit("")).alias("hire_rounds"),
        coalesce(col("main_tasks"), lit("")).alias("main_tasks"),
        coalesce(col("requirements"), lit("")).alias("requirements"),
        coalesce(col("preferred_points"), lit("")).alias("preferred_points"),
    )

    init_qdrant_collection(runtime_config)

    logger.info("Embedding 및 Qdrant upsert를 시작합니다.")
    target_rdd = cast("RDD[Any]", target_df.rdd)
    partition_counts = target_rdd.mapPartitions(
        lambda it: process_partition(it, runtime_config)
    ).collect()
    total_points = sum(partition_counts)

    logger.info("Gold 적재 완료: 총 %s건 벡터 upsert", total_points)
    spark.stop()


if __name__ == "__main__":
    run_upsert_gold()

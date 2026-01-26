import sys
import os
from pyspark.sql.functions import col, lit, coalesce, concat_ws
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from utils.spark_session import create_spark_session

COLLECTION_NAME = "career_jobs"
VECTOR_SIZE = 768
QDRANT_HOST = "mentoai-qdrant"
QDRANT_PORT = 6333

def get_postgres_properties():
    return {
        "user": os.getenv("DB_USER", "airflow"),
        "password": os.getenv("DB_PASSWORD", "airflow"),
        "driver": "org.postgresql.Driver"
    }

def init_qdrant_collection():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if not client.collection_exists(collection_name=COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE, 
                distance=models.Distance.COSINE
            )
        )
        print(" 컬렉션 생성 완료!")

def process_partition(iterator):

    model = SentenceTransformer('BM-K/KoSimCSE-roberta-multitask')
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    
    points = []
    for row in iterator:
        
        skills_str = ", ".join(row.skill_tags) if row.skill_tags else "없음"
        
        context_text = f"""
        [회사] {row.company}
        [포지션] {row.position}
        [경력요건] {row.annual_from}년 ~ {row.annual_to}년
        [기술스택] {skills_str}
        [주요업무] {row.main_tasks}
        [자격요건] {row.requirements}
        [우대사항] {row.preferred_points}
        """.strip()
        
        embedding_vector = model.encode(context_text).tolist()
        
    
        payload = {
            "id": row.id,
            "company": row.company,
            "position": row.position,
            "is_newbie": row.is_newbie,
            "annual_from": row.annual_from,
            "annual_to": row.annual_to,
            "skills": skills_str,          
            "intro": row.intro,            
            "hire_rounds": row.hire_rounds,
            "full_text": context_text
        }
        

        point = models.PointStruct(
            id=row.id,
            vector=embedding_vector,
            payload=payload
        )
        points.append(point)
    
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
    
    yield len(points)

def run_upsert_gold():
    spark = create_spark_session("MentoAI_Job3_Gold")
    
    db_url = os.getenv("DB_URL", "jdbc:postgresql://postgres:5432/mentoai")
    
    print("📂 Reading from Postgres Silver Layer...")
    silver_df = spark.read.jdbc(
        url=db_url,
        table="career_jobs",
        properties=get_postgres_properties()
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
        coalesce(col("preferred_points"), lit("")).alias("preferred_points")
    )
    
    init_qdrant_collection()
    
    print("🚀 Embedding & Indexing 시작...")
    count = target_df.rdd.mapPartitions(process_partition).count()
    
    print(f"🎉 작업 완료! 총 처리된 파티션 수: {count}")
    spark.stop()

if __name__ == "__main__":
    run_upsert_gold()
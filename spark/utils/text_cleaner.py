from pyspark.sql.types import StructType, StructField, StringType, IntegerType, ArrayType, BooleanType
from pyspark.sql.functions import from_json, col, to_date, coalesce, lit


DETAIL_SCHEMA = StructType([
    StructField("position", StringType()),
    StructField("intro", StringType()),
    StructField("main_tasks", StringType()),
    StructField("requirements", StringType()),
    StructField("preferred_points", StringType()),
    StructField("benefits", StringType()),
    StructField("hire_rounds", StringType())
])

RAW_DATA_SCHEMA = StructType([
    StructField("id", IntegerType()),
    StructField("status", StringType()),
    StructField("is_newbie", BooleanType()),
    StructField("employment_type", StringType()),
    StructField("annual_from", IntegerType()),
    StructField("annual_to", IntegerType()),
    StructField("due_time", StringType()),
    StructField("address", StructType([StructField("full_location", StringType())])),
    StructField("detail", DETAIL_SCHEMA),
    StructField("company", StructType([StructField("name", StringType())])),
    StructField("skill_tags", ArrayType(StringType()))
])

OUTER_SCHEMA = StructType([
    StructField("source", StringType()),
    StructField("collected_at", StringType()),
    StructField("raw_data", RAW_DATA_SCHEMA)
])

def clean_job_details(raw_df):

    # JSON 전체 파싱
    parsed_df = raw_df.select(from_json(col("value"), OUTER_SCHEMA).alias("data")).select("data.*")

    # 필드 추출 및 가공
    flattened_df = parsed_df.select(
        col("raw_data.id").alias("id"),
        col("raw_data.status").alias("status"),
        col("raw_data.company.name").alias("company"),
        col("raw_data.address.full_location").alias("location"), 
        col("raw_data.detail.position").alias("position"),
        col("raw_data.detail.intro").alias("intro"),
        col("raw_data.detail.main_tasks").alias("main_tasks"),
        col("raw_data.detail.requirements").alias("requirements"),
        col("raw_data.detail.preferred_points").alias("preferred_points"),
        col("raw_data.detail.benefits").alias("benefits"),
        col("raw_data.detail.hire_rounds").alias("hire_rounds"),
        coalesce(col("raw_data.due_time"), lit("상시채용")).alias("due_time"), 
        col("raw_data.is_newbie").alias("is_newbie"),
        col("raw_data.employment_type").alias("employment_type"),
        col("raw_data.annual_from").alias("annual_from"),
        col("raw_data.annual_to").alias("annual_to"),
        col("raw_data.skill_tags").alias("skill_tags"),
        col("collected_at")
    )

    # 날짜 변환 및 중복 제거
    cleaned_df = flattened_df.withColumn("collected_date", to_date(col("collected_at")))
    
    return cleaned_df.dropDuplicates(["id"])
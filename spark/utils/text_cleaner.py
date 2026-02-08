from pyspark.sql import DataFrame
from pyspark.sql.functions import (
    coalesce,
    col,
    concat_ws,
    from_json,
    lit,
    regexp_extract,
    to_date,
    when,
    xxhash64,
)
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


DETAIL_SCHEMA = StructType(
    [
        StructField("position", StringType()),
        StructField("intro", StringType()),
        StructField("main_tasks", StringType()),
        StructField("requirements", StringType()),
        StructField("preferred_points", StringType()),
        StructField("benefits", StringType()),
        StructField("hire_rounds", StringType()),
    ]
)

RAW_DATA_SCHEMA = StructType(
    [
        StructField("id", IntegerType()),
        StructField("status", StringType()),
        StructField("is_newbie", BooleanType()),
        StructField("employment_type", StringType()),
        StructField("annual_from", IntegerType()),
        StructField("annual_to", IntegerType()),
        StructField("due_time", StringType()),
        StructField(
            "address", StructType([StructField("full_location", StringType())])
        ),
        StructField("detail", DETAIL_SCHEMA),
        StructField("company", StructType([StructField("name", StringType())])),
        StructField("skill_tags", ArrayType(StringType())),
    ]
)

OUTER_SCHEMA = StructType(
    [
        StructField("source", StringType()),
        StructField("source_id", StringType()),
        StructField("collected_at", StringType()),
        StructField("raw_data", RAW_DATA_SCHEMA),
        StructField("company", StringType()),
        StructField("title", StringType()),
        StructField("location", StringType()),
        StructField("description", StringType()),
        StructField("requirements", StringType()),
        StructField("preferred_qualifications", StringType()),
        StructField("deadline", StringType()),
        StructField("reg_date", StringType()),
        StructField("link", StringType()),
        StructField("pay", StringType()),
    ]
)


def clean_job_details(raw_df: DataFrame) -> DataFrame:
    parsed_df = raw_df.select(
        from_json(col("value"), OUTER_SCHEMA).alias("data")
    ).select("data.*")

    source_col = coalesce(
        col("source"),
        when(col("raw_data").isNotNull(), lit("wanted")),
        lit("recruit24"),
    )
    source_id_col = coalesce(col("source_id"), col("raw_data.id").cast("string"))
    extracted_numeric_id = regexp_extract(
        coalesce(source_id_col, lit("")), r"(\d+)", 1
    ).cast("long")
    fallback_hash_id = xxhash64(
        coalesce(source_id_col, lit("")),
        coalesce(col("title"), lit("")),
        coalesce(col("company"), lit("")),
        coalesce(col("collected_at"), lit("")),
    )

    flattened_df = parsed_df.select(
        coalesce(
            col("raw_data.id").cast("long"), extracted_numeric_id, fallback_hash_id
        ).alias("id"),
        source_col.alias("source"),
        source_id_col.alias("source_id"),
        coalesce(col("raw_data.status"), lit("active")).alias("status"),
        coalesce(col("raw_data.company.name"), col("company"), lit("N/A")).alias(
            "company"
        ),
        coalesce(
            col("raw_data.address.full_location"), col("location"), lit("지역 미상")
        ).alias("location"),
        coalesce(col("raw_data.detail.position"), col("title"), lit("N/A")).alias(
            "position"
        ),
        coalesce(col("raw_data.detail.intro"), col("description"), lit("")).alias(
            "intro"
        ),
        coalesce(col("raw_data.detail.main_tasks"), col("description"), lit("")).alias(
            "main_tasks"
        ),
        coalesce(
            col("raw_data.detail.requirements"), col("requirements"), lit("")
        ).alias("requirements"),
        coalesce(
            col("raw_data.detail.preferred_points"),
            col("preferred_qualifications"),
            lit(""),
        ).alias("preferred_points"),
        coalesce(col("raw_data.detail.benefits"), lit("")).alias("benefits"),
        coalesce(col("raw_data.detail.hire_rounds"), lit("")).alias("hire_rounds"),
        coalesce(col("raw_data.due_time"), col("deadline"), lit("상시채용")).alias(
            "due_time"
        ),
        col("raw_data.is_newbie").alias("is_newbie"),
        col("raw_data.employment_type").alias("employment_type"),
        col("raw_data.annual_from").alias("annual_from"),
        col("raw_data.annual_to").alias("annual_to"),
        col("raw_data.skill_tags").alias("skill_tags"),
        col("collected_at"),
    )

    cleaned_df = (
        flattened_df.withColumn("collected_date", to_date(col("collected_at")))
        .withColumn(
            "job_key",
            coalesce(
                when(
                    col("source_id").isNotNull(),
                    concat_ws(":", col("source"), col("source_id")),
                ),
                concat_ws(":", col("source"), col("id").cast("string")),
            ),
        )
        .dropDuplicates(["job_key"])
        .drop("job_key", "source", "source_id")
    )

    return cleaned_df

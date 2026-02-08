from pyspark.sql import SparkSession

from utils.config import SparkRuntimeConfig


def create_spark_session(
    app_name: str,
    runtime_config: SparkRuntimeConfig,
    master: str = "local[*]",
) -> SparkSession:
    packages = [
        "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0",
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
        "org.postgresql:postgresql:42.6.0",
    ]

    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.jars.packages", ",".join(packages))
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config(
            "spark.hadoop.fs.s3a.endpoint",
            f"s3.{runtime_config.aws_region}.amazonaws.com",
        )
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
    )

    if runtime_config.aws_access_key_id:
        builder = builder.config(
            "spark.hadoop.fs.s3a.access.key", runtime_config.aws_access_key_id
        )
    if runtime_config.aws_secret_access_key:
        builder = builder.config(
            "spark.hadoop.fs.s3a.secret.key", runtime_config.aws_secret_access_key
        )

    spark = builder.getOrCreate()
    spark_context = getattr(spark, "sparkContext", None)
    if spark_context is not None:
        spark_context.setLogLevel("WARN")
    return spark

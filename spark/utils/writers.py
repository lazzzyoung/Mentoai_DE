import os

# Kafka -> S3 Bronze (Raw Data)
def write_raw_to_s3(df):

    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3_path = f"s3a://{bucket_name}/bronze/career_raw/"
    checkpoint_path = f"s3a://{bucket_name}/bronze/checkpoints/career_raw/"

    print(f"💾 Saving Raw Data to S3: {s3_path}")

    return df.writeStream \
        .format("parquet") \
        .outputMode("append") \
        .partitionBy("collected_date") \
        .option("path", s3_path) \
        .option("checkpointLocation", checkpoint_path) \
        .trigger(availableNow=True) \
        .start()

def _write_to_postgres_batch(batch_df, batch_id):
    
    db_url = os.getenv("DB_URL", "jdbc:postgresql://postgres:5432/mentoai")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_table = "career_jobs"

    if batch_df.count() > 0:
        batch_df.write \
            .format("jdbc") \
            .option("url", db_url) \
            .option("dbtable", db_table) \
            .option("user", db_user) \
            .option("password", db_password) \
            .option("driver", "org.postgresql.Driver") \
            .mode("append") \
            .save()
        print(f" DB Saved Batch ID: {batch_id} | Count: {batch_df.count()}")

# S3 Bronze -> Postgres Silver
def write_to_postgres(df):
    
    bucket_name = os.getenv("S3_BUCKET_NAME")
    checkpoint_path = f"s3a://{bucket_name}/silver/checkpoints/postgres_career/"

    print(f"💾 Saving Processed Data to Postgres")

    return df.writeStream \
        .foreachBatch(_write_to_postgres_batch) \
        .option("checkpointLocation", checkpoint_path) \
        .trigger(availableNow=True) \
        .start()
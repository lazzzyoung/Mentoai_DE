FROM apache/spark-py:v3.5.0

USER root

RUN pip install --no-cache-dir uv

WORKDIR /opt/airflow

COPY pyproject.toml ./

RUN UV_CACHE_DIR=/tmp/uv-cache \
    uv pip install --system --break-system-packages --group spark --torch-backend cpu --project /opt/airflow

USER spark

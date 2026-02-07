FROM apache/airflow:2.8.1

USER root

RUN apt-get update && \
    apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    pip install --no-cache-dir uv && \
    chmod 666 /var/run/docker.sock || true

WORKDIR /opt/airflow

COPY pyproject.toml uv.lock ./

RUN UV_CACHE_DIR=/tmp/uv-cache \
    uv export --frozen --no-emit-project --only-group airflow \
    --format requirements.txt --output-file /tmp/airflow-requirements.txt --project /opt/airflow && \
    uv pip install --system --break-system-packages --requirements /tmp/airflow-requirements.txt && \
    rm -f /tmp/airflow-requirements.txt

USER airflow

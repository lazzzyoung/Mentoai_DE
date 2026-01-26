FROM apache/spark-py:latest

USER root

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

USER spark
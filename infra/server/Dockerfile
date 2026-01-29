FROM python:3.10-slim

WORKDIR /app

# 시스템 의존성 설치 (Postgres 연결용)
RUN apt-get update && apt-get install -y libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*

# 경로 변경에 따른 requirements 복사
# (docker-compose에서 context를 프로젝트 루트로 잡을 예정이므로 경로를 맞춰줍니다)
COPY infra/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "from langchain_huggingface import HuggingFaceEmbeddings; HuggingFaceEmbeddings(model_name='BM-K/KoSimCSE-roberta-multitask')"

# 소스코드 복사 (루트의 server 폴더를 컨테이너의 /app/server로 복사)
COPY server/ ./server/

# FastAPI 실행 (server.app.main 모듈 실행)
CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
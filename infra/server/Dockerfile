FROM python:3.11-slim

WORKDIR /app

# 경로 변경에 따른 requirements 복사
# (docker-compose에서 context를 프로젝트 루트로 잡을 예정이므로 경로를 맞춰줍니다)
COPY infra/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스코드 복사 (루트의 server 폴더를 컨테이너의 /app/server로 복사)
COPY server/ ./server/

# FastAPI 실행 (server.app.main 모듈 실행)
CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

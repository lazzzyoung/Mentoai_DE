# Lightsail 4GB 배포 가이드 (SQLite + uv)

## 1) 코드 준비
```bash
cd ~
git clone <YOUR_REPO_URL> Mentoai_DE
cd ~/Mentoai_DE
```

## 2) 서버 초기 설정
```bash
chmod +x setup_ubuntu.sh
bash setup_ubuntu.sh
```

설치 항목:
- swap (8GB)
- uv
- Python 3.12
- sqlite3
- certbot

## 3) 프로젝트 의존성 및 환경 변수
```bash
uv sync
uv run poe env-init
```

`.env`에서 반드시 설정:
- `OPENAI_API_KEY`
- `SQLITE_DB_PATH` (기본 `./data/mentoai.db`)
- `CRAWLER_INTERVAL_MINUTES`

## 4) 서비스 실행
터미널 1:
```bash
uv run poe run-server
```

터미널 2:
```bash
uv run poe run-scheduler
```

상태 확인:
```bash
curl -fsS http://localhost:8000/health
```

## 5) HTTPS 설정 (도메인)
```bash
chmod +x setup_https_domain_only.sh
bash setup_https_domain_only.sh <DOMAIN> <EMAIL> /home/ubuntu/Mentoai_DE
```

완료 후:
```bash
curl -i https://<DOMAIN>/health
```

## 6) 운영 명령
```bash
# 크롤러 1회 실행
uv run poe crawl-once

# 품질 검사
uv run poe check
```


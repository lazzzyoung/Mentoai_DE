# Lightsail 4GB 초기 세팅부터 파이프라인 1회 실행까지

이 문서는 **Ubuntu Lightsail 4GB 서버**에서 MentoAI_DE를 처음 세팅하고,  
최종적으로 **파이프라인 1회 실행**(`pipeline-once-headless`)까지 진행하는 순서를 정리합니다.

---

## 0) 준비물

- 서버: Ubuntu (권장: 24.04, amd64)
- 도메인: 예) `mentoai.kro.kr`
- 이메일: 예) `jschae02@khu.ac.kr`
- Lightsail 방화벽:
  - 인바운드 허용: `22`, `80`, `443`
  - `8000`은 외부 오픈 비권장

---

## 1) 코드 받기

```bash
cd ~
git clone <YOUR_REPO_URL> Mentoai_DE
cd ~/Mentoai_DE
```

---

## 2) 서버 초기 세팅 (반복 실행 가능)

`setup_ubuntu.sh`는 여러 번 실행해도 안전하도록(idempotent) 작성되어 있습니다.

```bash
chmod +x setup_ubuntu.sh
bash setup_ubuntu.sh
```

설치 내용:
- 16GB swap
- uv
- Python 3.12
- Docker + docker compose plugin
- certbot

> docker 그룹 반영을 위해 1회 재로그인(또는 `newgrp docker`) 권장

확인:
```bash
docker info
uv --version
python3 --version
certbot --version
```

---

## 3) 환경변수 준비

```bash
uv sync
uv run poe env-init
```

`.env`에서 최소 확인:
- `OPENAI_API_KEY`
- (필요 시) `OPENAI_MODEL`
- 기본 DB/Kafka/MinIO 값은 템플릿 기본값 사용 가능

---

## 4) 저사양 코어 서비스 기동

```bash
uv run poe docker-start
```

이 task는 코어 서비스만 올립니다:
- `postgres`
- `qdrant`
- `ai-server`

확인:
```bash
docker ps
curl -fsS http://localhost:8000/health
```

---

## 5) HTTPS 적용 (도메인 제한 + 인증서)

DNS 먼저 확인:
- `mentoai.kro.kr` A 레코드가 서버 공인 IP를 가리켜야 함
- `www.mentoai.kro.kr`는 있으면 자동 포함, 없으면 자동 스킵

실행:
```bash
chmod +x setup_https_domain_only.sh
./setup_https_domain_only.sh mentoai.kro.kr jschae02@khu.ac.kr /home/ubuntu/Mentoai_DE
```

이 스크립트가 수행하는 것:
- certbot 인증서 발급
- FastAPI `TrustedHostMiddleware` 적용
- `.env`의 `ALLOWED_HOSTS` 반영
- `ai-server`를 TLS로 재기동
- **host `443 -> ai-server:8000` 직접 바인딩**
- 과거 iptables `443/80 REDIRECT` 규칙 정리(외부 HTTPS 차단 문제 예방)

검증:
```bash
curl -i https://mentoai.kro.kr/health
sudo certbot renew --dry-run
```

---

## 6) 파이프라인 1회 실행 (저사양 권장)

가장 가벼운 1회 실행:
```bash
uv run poe pipeline-once-headless
```

동작:
- 파이프라인에 필요한 컨테이너만 임시 기동
- `mentoai_pipeline` DAG를 스케줄러 기반으로 1회 트리거/대기
- 종료 시 파이프라인 컨테이너 자동 정리
- `postgres`, `qdrant`는 서비스용으로 유지됨

---

## 7) 수집기만 1회 실행 (옵션)

```bash
uv run poe collect-once
```

---

## 8) 자주 쓰는 운영 명령어

```bash
# 코어 서비스 상태
uv run poe docker-ps

# 코어 서비스 재기동
uv run poe docker-start

# 전체 종료
uv run poe docker-down

# 로그 보기
uv run poe docker-logs
```

---

## 9) 트러블슈팅

### A. certbot 인증 실패
- `NXDOMAIN`: DNS 레코드 없음 → 도메인 A/CNAME 먼저 설정
- `unauthorized`/`404`: 80 포트 경로가 certbot으로 안 감 → 방화벽/포트 점유 확인

확인:
```bash
dig +short mentoai.kro.kr
sudo ss -ltnp | grep ':80' || true
```

### B. docker build 중 torch 다운로드 실패 (`Network is unreachable`)
원인 대부분: 과거 iptables 443 REDIRECT 규칙으로 컨테이너 외부 HTTPS가 막힘

응급 정리:
```bash
sudo iptables -t nat -D PREROUTING -p tcp --dport 443 -j REDIRECT --to-ports 8000 2>/dev/null || true
sudo iptables -t nat -D OUTPUT -p tcp -o lo --dport 443 -j REDIRECT --to-ports 8000 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true
```

### C. Airflow `Permission denied: /opt/airflow/logs`
원인: 호스트 bind mount 권한으로 Airflow가 로그 디렉터리를 쓰지 못함

최신 poe task는 실행 전에 자동으로 로그 디렉터리 권한을 보정합니다.  
구버전 스크립트에서 바로 응급 조치하려면:
```bash
mkdir -p ~/Mentoai_DE/logs/scheduler ~/Mentoai_DE/logs/webserver ~/Mentoai_DE/logs/dag_processor_manager
chmod -R 777 ~/Mentoai_DE/logs
```

---

## 10) 권장 실행 순서 요약

```bash
cd ~/Mentoai_DE
bash setup_ubuntu.sh
uv sync
uv run poe env-init
uv run poe docker-start
./setup_https_domain_only.sh mentoai.kro.kr jschae02@khu.ac.kr /home/ubuntu/Mentoai_DE
uv run poe pipeline-once-headless
```

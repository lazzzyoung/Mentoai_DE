#!/usr/bin/env bash
set -euo pipefail

# 목적:
# - nginx 없이 443 -> 8000 리다이렉트
# - Let's Encrypt 인증서 적용
# - FastAPI에서 특정 도메인 Host 헤더만 허용(TrustedHostMiddleware)
#
# 사용법:
#   bash setup_https_domain_only.sh <DOMAIN> <EMAIL> [PROJECT_DIR]
# 예시:
#   bash setup_https_domain_only.sh api.example.com admin@example.com /home/ubuntu/Mentoai_DE

DOMAIN="${1:?도메인을 넣어주세요. 예: api.example.com}"
EMAIL="${2:?이메일을 넣어주세요. 예: admin@example.com}"
PROJECT_DIR="${3:-$HOME/Mentoai_DE}"
WWW_DOMAIN=""

INFRA_DIR="$PROJECT_DIR/infra"
MAIN_PY="$PROJECT_DIR/server/app/main.py"
ENV_FILE="$PROJECT_DIR/.env"
OVERRIDE_FILE="$INFRA_DIR/docker-compose.tls.yml"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "필수 명령어 없음: $1"; exit 1; }
}

has_dns_record() {
  local host="$1"
  getent ahosts "$host" >/dev/null 2>&1
}

add_iptables_rule() {
  # 중복 추가 방지
  local table="$1"; shift
  if ! sudo iptables -t "$table" -C "$@" 2>/dev/null; then
    sudo iptables -t "$table" -A "$@"
  fi
}

del_iptables_rule_if_exists() {
  local table="$1"; shift
  if sudo iptables -t "$table" -C "$@" 2>/dev/null; then
    sudo iptables -t "$table" -D "$@"
  fi
}

require_cmd docker
require_cmd python3
require_cmd certbot
require_cmd getent

if [[ ! -f "$INFRA_DIR/docker-compose.yml" ]]; then
  echo "docker-compose.yml을 찾을 수 없습니다: $INFRA_DIR/docker-compose.yml"
  exit 1
fi
if [[ ! -f "$MAIN_PY" ]]; then
  echo "main.py를 찾을 수 없습니다: $MAIN_PY"
  exit 1
fi

if [[ "$DOMAIN" != www.* ]]; then
  candidate_www="www.$DOMAIN"
  if has_dns_record "$candidate_www"; then
    WWW_DOMAIN="$candidate_www"
  else
    echo "알림: $candidate_www DNS 레코드가 없어 www 인증서는 건너뜁니다."
  fi
fi

if [[ -n "$WWW_DOMAIN" ]]; then
  ALLOWED_HOSTS_VALUE="$DOMAIN,$WWW_DOMAIN,localhost,127.0.0.1"
else
  ALLOWED_HOSTS_VALUE="$DOMAIN,localhost,127.0.0.1"
fi

echo "[0/7] certbot standalone 방해 가능 규칙 정리(80->8000 리다이렉트 제거)"
del_iptables_rule_if_exists nat PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 8000
del_iptables_rule_if_exists nat OUTPUT -p tcp -o lo --dport 80 -j REDIRECT --to-ports 8000

echo "[1/7] Let's Encrypt 인증서 발급(또는 갱신)"
CERTBOT_DOMAIN_ARGS=(-d "$DOMAIN")
if [[ -n "$WWW_DOMAIN" ]]; then
  CERTBOT_DOMAIN_ARGS+=(-d "$WWW_DOMAIN")
fi

sudo certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL" \
  "${CERTBOT_DOMAIN_ARGS[@]}" \
  --keep-until-expiring \
  --preferred-challenges http

echo "[2/7] FastAPI TrustedHostMiddleware 패치(도메인 제한)"
python3 - <<PY
from pathlib import Path

p = Path(r"$MAIN_PY")
text = p.read_text(encoding="utf-8")
original = text

# import os
if "import os\n" not in text:
    text = text.replace("import logging\n", "import logging\nimport os\n", 1)

# TrustedHostMiddleware import
trusted_import = "from starlette.middleware.trustedhost import TrustedHostMiddleware\n"
if trusted_import not in text:
    text = text.replace(
        "from fastapi.staticfiles import StaticFiles\n",
        "from fastapi.staticfiles import StaticFiles\n" + trusted_import,
        1,
    )

# middleware injection
needle = "    app = FastAPI(title=\"MentoAI RAG Server\", lifespan=lifespan)\n"
inject = (
    "    allowed_hosts = [host.strip() for host in os.getenv(\"ALLOWED_HOSTS\", \"\").split(\",\") if host.strip()]\n"
    "    if allowed_hosts:\n"
    "        app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)\n"
)
if "app.add_middleware(TrustedHostMiddleware" not in text:
    if needle in text:
        text = text.replace(needle, needle + inject, 1)
    else:
        raise SystemExit("main.py 구조가 예상과 달라 자동 패치에 실패했습니다.")

if text != original:
    p.write_text(text, encoding="utf-8")
    print("main.py 패치 완료")
else:
    print("main.py 이미 패치되어 있음")
PY

echo "[3/7] .env에 ALLOWED_HOSTS 설정"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"
if grep -q '^ALLOWED_HOSTS=' "$ENV_FILE"; then
  sed -i.bak "s|^ALLOWED_HOSTS=.*$|ALLOWED_HOSTS=$ALLOWED_HOSTS_VALUE|" "$ENV_FILE"
else
  echo "ALLOWED_HOSTS=$ALLOWED_HOSTS_VALUE" >> "$ENV_FILE"
fi

echo "[4/7] TLS용 compose override 파일 생성"
cat > "$OVERRIDE_FILE" <<YAML
services:
  ai-server:
    volumes:
      - ../server:/app/server
      - /etc/letsencrypt:/etc/letsencrypt:ro
    command: >
      uvicorn server.app.main:app --host 0.0.0.0 --port 8000
      --ssl-keyfile /etc/letsencrypt/live/$DOMAIN/privkey.pem
      --ssl-certfile /etc/letsencrypt/live/$DOMAIN/fullchain.pem
YAML

echo "[5/7] ai-server 재기동 (TLS 적용)"
(
  cd "$INFRA_DIR"
  docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --force-recreate ai-server
)

echo "[6/7] Linux 레벨 443 -> 8000 리다이렉트"
add_iptables_rule nat PREROUTING -p tcp --dport 443 -j REDIRECT --to-ports 8000
add_iptables_rule nat OUTPUT -p tcp -o lo --dport 443 -j REDIRECT --to-ports 8000

# 규칙 영속화(가능한 경우)
if command -v netfilter-persistent >/dev/null 2>&1; then
  sudo netfilter-persistent save
fi

echo "[7/7] 인증서 갱신 후 자동 재기동 hook 등록"
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/mentoai-ai-server-reload.sh >/dev/null <<HOOK
#!/usr/bin/env bash
set -euo pipefail
cd "$INFRA_DIR"
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --force-recreate ai-server
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/mentoai-ai-server-reload.sh

echo
echo "완료: https://$DOMAIN/health"
if [[ -n "$WWW_DOMAIN" ]]; then
  echo "완료: https://$WWW_DOMAIN/health"
fi
echo "주의1) Lightsail 방화벽에서 80/443 허용 필요"
echo "주의2) 8000 포트는 외부에서 닫는 것을 권장(방화벽)"

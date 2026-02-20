#!/usr/bin/env bash
set -euo pipefail

# 목적:
# - nginx 없이 uvicorn 단독 HTTPS 실행
# - Let's Encrypt 인증서 발급/갱신
# - FastAPI에서 ALLOWED_HOSTS를 환경변수로 제한
#
# 사용법:
#   bash setup_https_domain_only.sh <DOMAIN> <EMAIL> [PROJECT_DIR]

DOMAIN="${1:?도메인을 넣어주세요. 예: api.example.com}"
EMAIL="${2:?이메일을 넣어주세요. 예: admin@example.com}"
PROJECT_DIR="${3:-$HOME/Mentoai_DE}"
ENV_FILE="$PROJECT_DIR/.env"
SERVICE_FILE="/etc/systemd/system/mentoai-api.service"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "필수 명령어 없음: $1"; exit 1; }
}

require_cmd certbot
require_cmd systemctl
require_cmd python3

if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
  echo "프로젝트 루트를 찾을 수 없습니다: $PROJECT_DIR"
  exit 1
fi

echo "[1/5] Let's Encrypt 인증서 발급(또는 갱신)"
sudo certbot certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL" \
  -d "$DOMAIN" \
  --keep-until-expiring \
  --preferred-challenges http

CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"

if [[ ! -f "$CERT_PATH" || ! -f "$KEY_PATH" ]]; then
  echo "인증서 파일을 확인할 수 없습니다."
  exit 1
fi

echo "[2/5] .env 업데이트"
touch "$ENV_FILE"
for entry in \
  "ALLOWED_HOSTS=$DOMAIN,localhost,127.0.0.1" \
  "SSL_CERTFILE=$CERT_PATH" \
  "SSL_KEYFILE=$KEY_PATH"; do
  key="${entry%%=*}"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i.bak "s|^${key}=.*$|${entry}|" "$ENV_FILE"
  else
    echo "$entry" >> "$ENV_FILE"
  fi
done

echo "[3/5] systemd 서비스 생성"
sudo tee "$SERVICE_FILE" >/dev/null <<UNIT
[Unit]
Description=MentoAI FastAPI HTTPS Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
Environment=PATH=/usr/bin:/bin:/root/.local/bin
ExecStart=/bin/bash -lc 'source $PROJECT_DIR/.env && uv run uvicorn server.app.main:app --host 0.0.0.0 --port 443 --ssl-certfile $CERT_PATH --ssl-keyfile $KEY_PATH'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable mentoai-api.service
sudo systemctl restart mentoai-api.service

echo "[4/5] certbot renew hook 등록"
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/mentoai-restart.sh >/dev/null <<HOOK
#!/usr/bin/env bash
set -euo pipefail
systemctl restart mentoai-api.service
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/mentoai-restart.sh

echo "[5/5] 완료"
echo "https://$DOMAIN/health"

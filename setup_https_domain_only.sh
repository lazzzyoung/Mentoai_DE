#!/usr/bin/env bash
set -euo pipefail

# 목적:
# - nginx 없이 uvicorn 단독 HTTPS 실행
# - Let's Encrypt 인증서 발급/갱신
# - FastAPI에서 ALLOWED_HOSTS를 환경변수로 제한
#
# 사용법:
#   bash setup_https_domain_only.sh <DOMAIN> <EMAIL> [PROJECT_DIR]

RAW_DOMAIN="${1:?도메인을 넣어주세요. 예: api.example.com}"
EMAIL="${2:?이메일을 넣어주세요. 예: admin@example.com}"
PROJECT_DIR="${3:-$HOME/Mentoai_DE}"
ENV_FILE="$PROJECT_DIR/.env"
SERVICE_FILE="/etc/systemd/system/mentoai-api.service"

normalize_domain() {
  local raw="$1"
  local normalized="$raw"
  normalized="${normalized#http://}"
  normalized="${normalized#https://}"
  normalized="${normalized%%/*}"
  normalized="${normalized%.}"
  normalized="$(printf '%s' "$normalized" | tr '[:upper:]' '[:lower:]')"
  printf '%s' "$normalized"
}

validate_domain() {
  local value="$1"
  local -a labels

  if [[ -z "$value" ]]; then
    echo "도메인이 비어 있습니다."
    return 1
  fi
  if [[ "$value" == *:* ]]; then
    echo "포트 번호를 포함하지 마세요. 예: api.example.com"
    return 1
  fi
  if [[ "$value" != *.* ]]; then
    echo "FQDN 형식이 아닙니다. 예: api.example.com"
    return 1
  fi
  if [[ "$value" =~ [^a-z0-9.-] ]]; then
    echo "도메인에 허용되지 않는 문자가 포함되어 있습니다: $value"
    return 1
  fi

  IFS='.' read -r -a labels <<< "$value"
  for label in "${labels[@]}"; do
    if [[ -z "$label" || ${#label} -gt 63 ]]; then
      echo "도메인 라벨 길이가 올바르지 않습니다: $value"
      return 1
    fi
    if [[ ! "$label" =~ ^[a-z0-9-]+$ ]]; then
      echo "도메인 라벨 형식이 올바르지 않습니다: $label"
      return 1
    fi
    if [[ "$label" == -* || "$label" == *- ]]; then
      echo "도메인 라벨은 하이픈으로 시작/종료할 수 없습니다: $label"
      return 1
    fi
  done

  return 0
}

DOMAIN="$(normalize_domain "$RAW_DOMAIN")"
if ! validate_domain "$DOMAIN"; then
  echo "입력 도메인: $RAW_DOMAIN"
  echo "올바른 예시: setup_https_domain_only.sh api.example.com admin@example.com"
  exit 1
fi
if [[ "$RAW_DOMAIN" != "$DOMAIN" ]]; then
  echo "도메인 입력을 정규화했습니다: $RAW_DOMAIN -> $DOMAIN"
fi

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

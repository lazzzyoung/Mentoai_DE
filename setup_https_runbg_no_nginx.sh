#!/usr/bin/env bash
set -euo pipefail

# 목적:
# - nginx 없이 run-bg(8000)를 HTTPS(443)로 노출
# - certbot(standalone)로 인증서 발급/갱신
# - stunnel로 443 -> 127.0.0.1:8000 TLS 프록시 구성
#
# 사용법:
#   bash setup_https_runbg_no_nginx.sh <DOMAIN> <EMAIL> [PROJECT_DIR]

RAW_DOMAIN="${1:?도메인을 넣어주세요. 예: api.example.com}"
EMAIL="${2:?이메일을 넣어주세요. 예: admin@example.com}"
PROJECT_DIR="${3:-$HOME/project}"
STUNNEL_CONF="/etc/stunnel/mentoai-https.conf"
RENEW_HOOK="/etc/letsencrypt/renewal-hooks/deploy/mentoai-restart-stunnel.sh"

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

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "필수 명령어 없음: $1"
    exit 1
  }
}

DOMAIN="$(normalize_domain "$RAW_DOMAIN")"
if ! validate_domain "$DOMAIN"; then
  echo "입력 도메인: $RAW_DOMAIN"
  echo "올바른 예시: setup_https_runbg_no_nginx.sh api.example.com admin@example.com /home/ubuntu/project"
  exit 1
fi
if [[ "$RAW_DOMAIN" != "$DOMAIN" ]]; then
  echo "도메인 입력을 정규화했습니다: $RAW_DOMAIN -> $DOMAIN"
fi

require_cmd sudo
require_cmd systemctl
require_cmd certbot
require_cmd uv

if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
  echo "프로젝트 루트를 찾을 수 없습니다: $PROJECT_DIR"
  exit 1
fi

echo "[1/7] 방화벽 포트 허용(80/443)"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 80/tcp >/dev/null || true
  sudo ufw allow 443/tcp >/dev/null || true
fi

echo "[2/7] 인증서 발급(또는 갱신)"
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

echo "[3/7] 기존 443 점유 서비스 정리(nginx/mentoai-api)"
sudo systemctl disable --now nginx >/dev/null 2>&1 || true
sudo systemctl disable --now mentoai-api.service >/dev/null 2>&1 || true

echo "[4/7] run-bg 실행(8000 + scheduler)"
cd "$PROJECT_DIR"
uv run poe run-bg

if ! ss -lnt | grep -q ':8000 '; then
  echo "포트 8000이 열려 있지 않습니다. logs/server.log 확인 후 다시 시도하세요."
  exit 1
fi

echo "[5/7] stunnel 설치/설정(443 -> 127.0.0.1:8000)"
sudo apt-get update -y
sudo apt-get install -y stunnel4

sudo tee "$STUNNEL_CONF" >/dev/null <<EOF
foreground = no
pid = /var/run/stunnel4/mentoai.pid
setuid = stunnel4
setgid = stunnel4
socket = l:TCP_NODELAY=1
socket = r:TCP_NODELAY=1

[mentoai-https]
accept = 0.0.0.0:443
connect = 127.0.0.1:8000
cert = $CERT_PATH
key = $KEY_PATH
EOF

if [[ -f /etc/default/stunnel4 ]]; then
  if grep -q '^ENABLED=' /etc/default/stunnel4; then
    sudo sed -i 's/^ENABLED=.*/ENABLED=1/' /etc/default/stunnel4
  else
    echo 'ENABLED=1' | sudo tee -a /etc/default/stunnel4 >/dev/null
  fi
fi

sudo systemctl enable stunnel4
sudo systemctl restart stunnel4

echo "[6/7] certbot 갱신 훅 등록(stunnel 재시작)"
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee "$RENEW_HOOK" >/dev/null <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
systemctl restart stunnel4
HOOK
sudo chmod +x "$RENEW_HOOK"

echo "[7/7] 상태 확인"
if ss -lnt | grep -q ':443 '; then
  echo "정상: 443 포트가 열렸습니다."
else
  echo "경고: 443 포트 리슨 상태를 확인하세요."
fi

echo "완료: https://$DOMAIN/health"
echo "로그 확인:"
echo "  tail -n 100 $PROJECT_DIR/logs/server.log"
echo "  tail -n 100 $PROJECT_DIR/logs/scheduler.log"

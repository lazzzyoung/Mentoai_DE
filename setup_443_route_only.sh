#!/usr/bin/env bash
set -euo pipefail

# 목적:
# - nginx 없이 443(HTTPS) -> 127.0.0.1:8000 라우팅만 설정
# - 인증서 발급/갱신은 수행하지 않음(기존 certbot 인증서 사용)
#
# 사용법:
#   bash setup_443_route_only.sh <DOMAIN> [PROJECT_DIR]
# 예시:
#   bash setup_443_route_only.sh mentoai.kro.kr /home/ubuntu/project

DOMAIN="${1:?도메인을 넣어주세요. 예: mentoai.kro.kr}"
PROJECT_DIR="${2:-$HOME/project}"

CERT_PATH="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"
KEY_PATH="/etc/letsencrypt/live/$DOMAIN/privkey.pem"
STUNNEL_CONF="/etc/stunnel/mentoai-https.conf"

if [[ ! -f "$PROJECT_DIR/pyproject.toml" ]]; then
  echo "프로젝트 루트를 찾을 수 없습니다: $PROJECT_DIR"
  exit 1
fi

if ! sudo test -f "$CERT_PATH"; then
  echo "인증서 파일이 없습니다: $CERT_PATH"
  exit 1
fi
if ! sudo test -f "$KEY_PATH"; then
  echo "개인키 파일이 없습니다: $KEY_PATH"
  exit 1
fi

echo "[1/5] run-bg 실행(8000 + scheduler)"
cd "$PROJECT_DIR"
uv run poe run-bg

if ! ss -lnt | grep -q ':8000 '; then
  echo "포트 8000이 열려 있지 않습니다. logs/server.log 확인 후 다시 시도하세요."
  exit 1
fi

echo "[2/5] 443 점유 가능 상태로 정리"
sudo systemctl disable --now nginx >/dev/null 2>&1 || true
sudo systemctl disable --now mentoai-api.service >/dev/null 2>&1 || true

echo "[3/5] stunnel 설치"
sudo apt-get update -y
sudo apt-get install -y stunnel4

echo "[4/5] stunnel 설정(443 -> 127.0.0.1:8000)"
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

echo "[5/5] stunnel 시작"
sudo systemctl enable stunnel4
sudo systemctl restart stunnel4

if ss -lnt | grep -q ':443 '; then
  echo "정상: 443 -> 8000 라우팅 활성화"
  echo "확인: https://$DOMAIN/health"
else
  echo "실패: 443 포트 리슨 상태를 확인하세요."
  exit 1
fi

#!/usr/bin/env bash
# MentoAI 네이티브 배포 (Docker 불필요 — 우분투 기본 패키지로 동작):
#   로컬 크로스컴파일 → rsync 전송 → systemd 서비스 + apt Caddy로 기동 → 헬스체크
#
# 사용법:
#   bash scripts/deploy-native.sh <user@host> [amd64|arm64] [ssh포트]
#   예: bash scripts/deploy-native.sh root@10.0.0.1 arm64 22
#
# 서버에 설치/구성되는 것:
#   - apt: caddy, rsync  (우분투 저장소 그대로)
#   - /opt/mentoai/  : 바이너리 + .env + data/ (전용 시스템 유저 mentoai 소유)
#   - systemd 유닛   : mentoai.service (자동 재시작)
#   - /etc/caddy/Caddyfile
#
# 전제: SSH 키 인증(또는 패스워드리스 sudo)이 되는 계정. 재실행해도 안전(멱등)하다.
set -euo pipefail

TARGET=${1:?대상 서버를 지정하세요: scripts/deploy-native.sh user@host [amd64|arm64] [port]}
ARCH=${2:-amd64}
SSH_PORT=${3:-22}
APP_DIR=/opt/mentoai
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new)
RSYNC_SSH="ssh -p ${SSH_PORT}"
if [[ -n ${SSH_KEY:-} ]]; then          # 선택: 전용 키 (SSH_KEY=~/.ssh/my_key ...)
  SSH_OPTS+=(-i "$SSH_KEY")
  RSYNC_SSH+=" -i $SSH_KEY"
fi

log()  { printf '\033[1;36m[mentoai-native]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[mentoai-native]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[mentoai-native]\033[0m %s\n' "$*" >&2; exit 1; }
# shellcheck disable=SC2029  # 의도: 일부 값은 클라이언트에서 확장해 서버로 보낸다
run()  { ssh "${SSH_OPTS[@]}" "$TARGET" "sudo sh -c '$*'"; }   # 서버에서 root 권한 실행

cd "$(dirname "$0")/.."

command -v rsync >/dev/null 2>&1 || die "로컬에 rsync 필요 (brew install rsync / apt install rsync)"
[[ -f Caddyfile ]] || die "저장소 루트에서 실행하세요 (Caddyfile 없음)"

# --- 1) 로컬 크로스컴파일 (CGO 없는 정적 바이너리) ---
log "linux/${ARCH} 정적 바이너리 빌드"
CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" \
  go build -trimpath -ldflags "-s -w" -o "dist/mentoai-linux-${ARCH}" ./cmd/mentoai

# --- 2) 서버 기본 패키지 (우분투 저장소 그대로) ---
log "서버 패키지 설치/확인: caddy · rsync · curl · openssl (apt)"
run "apt-get update -qq && apt-get install -y -qq caddy rsync curl openssl"

# --- 3) 전용 시스템 유저 + 디렉터리 ---
run "id -u mentoai >/dev/null 2>&1 || useradd --system --home ${APP_DIR} --shell /usr/sbin/nologin mentoai"
run "mkdir -p ${APP_DIR}/data"

# --- 4) 바이너리 교체 (임시 업로드 후 install — 실행 중 파일 교체 안전) ---
log "바이너리 전송 (${ARCH})"
rsync -e "${RSYNC_SSH}" "dist/mentoai-linux-${ARCH}" "${TARGET}:/tmp/mentoai-bin"
run "install -m 0755 /tmp/mentoai-bin ${APP_DIR}/mentoai && rm -f /tmp/mentoai-bin"

# --- 5) .env: 서버에 없을 때만 올린다 (기존 서버 설정은 절대 덮지 않는다) ---
# shellcheck disable=SC2029  # 의도: 클라이언트 확장
if ! ssh "${SSH_OPTS[@]}" "$TARGET" "test -f ${APP_DIR}/.env"; then # shellcheck disable=SC2029
  log "서버에 .env가 없다 — 로컬 파일을 올리고 AUTH_SECRET 발급"
  if [[ -f .env ]]; then
    rsync -e "${RSYNC_SSH}" .env "${TARGET}:/tmp/mentoai-env"
  else
    rsync -e "${RSYNC_SSH}" .env.example "${TARGET}:/tmp/mentoai-env"
  fi
  run "install -m 0600 -o mentoai -g mentoai /tmp/mentoai-env ${APP_DIR}/.env && rm -f /tmp/mentoai-env"
  run "grep -q \"^AUTH_SECRET=..\" ${APP_DIR}/.env || printf \"AUTH_SECRET=%s\n\" \"\$(openssl rand -hex 32)\" >> ${APP_DIR}/.env"
else
  log ".env 유지 (기존 서버 설정 보존)"
fi

# --- 6) systemd 유닛 설치 ---
log "systemd 서비스 설치 (mentoai.service)"
# shellcheck disable=SC2087  # 의도: APP_DIR 등은 클라이언트에서 확장해 유닛에 박는다
ssh "${SSH_OPTS[@]}" "$TARGET" "sudo tee /etc/systemd/system/mentoai.service > /dev/null" <<EOF
[Unit]
Description=MentoAI career roadmap service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=mentoai
Group=mentoai
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/mentoai serve --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
# .env는 앱이 WorkingDirectory에서 직접 읽는다 (SQLITE_PATH·키 등 전부 반영)
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}/data

[Install]
WantedBy=multi-user.target
EOF

run "chown -R mentoai:mentoai ${APP_DIR}"
run "chmod 600 ${APP_DIR}/.env"
run "systemctl daemon-reload && systemctl enable --now mentoai && systemctl restart mentoai"

# --- 7) Caddy 설정: 도메인을 박아 넣고 검증 후 반영 ---
DOMAIN=$(grep -E '^CADDY_DOMAIN=' .env 2>/dev/null | cut -d= -f2- | tr -d ' "'"'"'' || true)
DOMAIN=${DOMAIN:-localhost}
log "Caddyfile 반영 (도메인: ${DOMAIN})"
mkdir -p dist
sed -e "s/{\$CADDY_DOMAIN}/${DOMAIN}/" -e "s/{\$API_UPSTREAM}/127.0.0.1:8000/" Caddyfile > dist/Caddyfile.native
rsync -e "${RSYNC_SSH}" dist/Caddyfile.native "${TARGET}:/etc/caddy/Caddyfile"
# 구버전 caddy(2.5 등)가 protocols 옵션을 모르면 해당 줄을 빼고 재검증 —
# HTTP/3는 TLS 사이트에서 2.6+ 기본 활성이라 실질 차이 없음.
run "caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 || \
     (sed -i "/protocols h1 h2 h3/d" /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile)"
run "systemctl enable --now caddy && systemctl restart caddy"

# --- 8) 헬스체크 (서버 로컬 기준, 최대 60초) ---
log "헬스체크: https://${DOMAIN} ..."
ok=""
for _ in $(seq 1 60); do
  # shellcheck disable=SC2029  # 의도: 클라이언트 확장
  if ssh "${SSH_OPTS[@]}" "$TARGET" \
    "curl -skf --resolve ${DOMAIN}:443:127.0.0.1 https://${DOMAIN}/health >/dev/null 2>&1"; then # shellcheck disable=SC2029
    ok=1
    break
  fi
  sleep 1
done
if [[ -z $ok ]]; then
  warn "헬스체크 실패 — 서버 로그:"
  ssh "${SSH_OPTS[@]}" "$TARGET" "sudo journalctl -u mentoai -n 20 --no-pager"
  exit 1
fi

run "systemctl is-active mentoai caddy"
log "배포 완료!"
echo ""
echo "  앱:      https://${DOMAIN}"
echo "  어드민:  https://${DOMAIN}/admin"
echo "  앱 로그: ssh ${TARGET} sudo journalctl -u mentoai -f"
echo "  재배포:  이 스크립트 다시 실행 (바이너리 교체 + 서비스 재시작)"

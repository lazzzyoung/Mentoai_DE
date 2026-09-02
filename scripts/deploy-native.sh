#!/usr/bin/env bash
# MentoAI 네이티브 배포 (Docker 불필요 — 우분투 기본 패키지로 동작):
#   로컬 크로스컴파일 → rsync 전송 → systemd 서비스 + apt Caddy로 기동 → 헬스체크
#
# 사용법:
#   bash scripts/deploy-native.sh <user@host> [amd64|arm64] [ssh포트]
#   예: bash scripts/deploy-native.sh root@10.0.0.1 arm64 22
#   선택: SSH_KEY=키파일 SWAP=1(512MB 인스턴스 권장) 환경변수 지원
#
# 전제: SSH 키 인증(또는 패스워드리스 sudo)이 되는 계정. 재실행해도 안전(멱등)하다.
set -euo pipefail

TARGET=${1:?대상 서버를 지정하세요: scripts/deploy-native.sh user@host [amd64|arm64] [port]}
ARCH=${2:-amd64}
SSH_PORT=${3:-22}
APP_DIR=/opt/mentoai
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)
RSYNC_SSH="ssh -p ${SSH_PORT}"
if [[ -n ${SSH_KEY:-} ]]; then          # 선택: 전용 키 (SSH_KEY=~/.ssh/my_key ...)
  SSH_OPTS+=(-i "$SSH_KEY")
  RSYNC_SSH+=" -i $SSH_KEY"
fi

cd "$(dirname "$0")/.." || exit 1
# shellcheck source=scripts/lib.sh
source scripts/lib.sh
# shellcheck disable=SC2034  # lib.sh step()에서 사용
STEP_TOTAL=10
title "네이티브 배포 (무도커) → $TARGET ($ARCH)"

command -v rsync >/dev/null 2>&1 || { err "로컬에 rsync가 없다"; hint "macOS: brew install rsync ㅣ 우분투: sudo apt install rsync"; exit 1; }
[[ -f Caddyfile ]] || die "저장소 루트에서 실행하세요 (Caddyfile 없음)"

# 서버에서 root 권한 실행 (sudo는 root 계정에서도 동작한다)
# shellcheck disable=SC2029  # 의도: 일부 값은 클라이언트에서 확장해 서버로 보낸다
run() { ssh "${SSH_OPTS[@]}" "$TARGET" "sudo sh -c '$*'"; }

# --- [1/8] 시크릿 사전 검사 ---
step "시크릿 사전 검사"
bash scripts/check-secrets.sh || die "시크릿 유출 징후 발견 — 배포 중단"

# --- [2/8] 서버 연결 확인 + 로컬 크로스컴파일 ---
step "서버 연결 확인 (ssh ${TARGET}, 포트 ${SSH_PORT})"
if ssh "${SSH_OPTS[@]}" "$TARGET" "echo ok" >/dev/null 2>&1; then
  ok "연결 성공"
else
  err "서버에 SSH로 접속하지 못했습니다 ($TARGET)"
  hint "Lightsail이면: 콘솔 'Account page'에서 기본 키(.pem)를 받아 chmod 400 키파일 후 SSH_KEY=키경로 지정"
  hint "계정명: 우분투 이미지는 root가 아니라 ubuntu — HOST=ubuntu@IP 로 시도"
  hint "아키텍처: 서버에서 uname -m 결과가 aarch64면 ARCH=arm64, x86_64면 amd64"
  hint "방화벽: SSH 포트가 열려 있는지 확인 (Lightsail 네트워킹 탭)"
  exit 1
fi
step "로컬 크로스컴파일 (linux/${ARCH} 정적 바이너리)"
CGO_ENABLED=0 GOOS=linux GOARCH="$ARCH" \
  go build -trimpath -ldflags "-s -w" -o "dist/mentoai-linux-${ARCH}" ./cmd/mentoai
ok "빌드 완료: dist/mentoai-linux-${ARCH}"

# --- [3/8] 서버 패키지 (우분투 저장소 그대로) ---
step "서버 패키지 설치/확인 (caddy · rsync · curl · openssl)"
run "apt-get update -qq && apt-get install -y -qq caddy rsync curl openssl"
ok "설치 완료"

# --- [4/8] 전용 유저·디렉터리 (+선택 스왑) ---
step "시스템 유저·디렉터리 준비"
run "id -u mentoai >/dev/null 2>&1 || useradd --system --home ${APP_DIR} --shell /usr/sbin/nologin mentoai"
run "mkdir -p ${APP_DIR}/data"
ok "유저(mentoai)·${APP_DIR}/data 준비"

if [[ ${SWAP:-0} == 1 ]]; then
  if ssh "${SSH_OPTS[@]}" "$TARGET" "swapon --show=NAME --noheadings | grep -q ."; then
    skip "스왑 이미 존재"
  else
    run "fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile"
    run "grep -qs '/swapfile' /etc/fstab || printf '/swapfile none swap sw 0 0\n' >> /etc/fstab"
    ok "1GB 스왑 생성 (/swapfile, 재부팅 후에도 유지)"
  fi
fi

# --- [5/8] 바이너리 전송 (실행 중 교체도 안전한 install 방식) ---
step "바이너리 전송"
rsync -e "${RSYNC_SSH}" "dist/mentoai-linux-${ARCH}" "${TARGET}:/tmp/mentoai-bin"
run "install -m 0755 /tmp/mentoai-bin ${APP_DIR}/mentoai && rm -f /tmp/mentoai-bin"
ok "교체 완료: ${APP_DIR}/mentoai"

# --- [6/8] .env (서버에 없을 때만 — 기존 설정은 절대 덮지 않는다) ---
step ".env 확인"
# shellcheck disable=SC2029  # 의도: 클라이언트 확장
if ! ssh "${SSH_OPTS[@]}" "$TARGET" "test -f ${APP_DIR}/.env"; then
  if [[ -f .env ]]; then
    rsync -e "${RSYNC_SSH}" .env "${TARGET}:/tmp/mentoai-env"
  else
    rsync -e "${RSYNC_SSH}" .env.example "${TARGET}:/tmp/mentoai-env"
  fi
  run "install -m 0600 -o mentoai -g mentoai /tmp/mentoai-env ${APP_DIR}/.env && rm -f /tmp/mentoai-env"
  run "grep -q \"^AUTH_SECRET=..\" ${APP_DIR}/.env || printf \"AUTH_SECRET=%s\n\" \"\$(openssl rand -hex 32)\" >> ${APP_DIR}/.env"
  ok ".env 새로 올렸다 (AUTH_SECRET 자동 발급 포함)"
  warn "GOOGLE_API_KEY 등은 서버의 ${APP_DIR}/.env에서 채우세요"
else
  ok ".env 유지 (기존 서버 설정 보존)"
fi

# --- [7/8] systemd 서비스 + Caddy ---
step "systemd 서비스 설치 (mentoai.service)"
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
ok "mentoai.service 등록·기동"

step "Caddy 설정 반영 (자동 HTTPS·HTTP/3)"
DOMAIN=$(grep -E '^CADDY_DOMAIN=' .env 2>/dev/null | cut -d= -f2- | tr -d ' "'"'"'' || true)
DOMAIN=${DOMAIN:-localhost}
mkdir -p dist
sed -e "s/{\$CADDY_DOMAIN}/${DOMAIN}/" -e "s/{\$API_UPSTREAM}/127.0.0.1:8000/" Caddyfile > dist/Caddyfile.native
rsync -e "${RSYNC_SSH}" dist/Caddyfile.native "${TARGET}:/etc/caddy/Caddyfile"
# 구버전 caddy(2.5 등)가 protocols 옵션을 모르면 해당 줄을 빼고 재검증 —
# HTTP/3는 TLS 사이트에서 2.6+ 기본 활성이라 실질 차이 없음.
run "caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1 || \
     (sed -i \"/protocols h1 h2 h3/d\" /etc/caddy/Caddyfile && caddy validate --config /etc/caddy/Caddyfile)"
run "systemctl enable --now caddy && systemctl restart caddy"
ok "Caddy 기동 (https://${DOMAIN})"

# --- [8/8] 헬스체크 ---
step "헬스체크 (최대 60초)"
ok=""
# shellcheck disable=SC2029  # 의도: 클라이언트 확장
for _ in $(seq 1 60); do
  if ssh "${SSH_OPTS[@]}" "$TARGET" \
    "curl -skf --resolve ${DOMAIN}:443:127.0.0.1 https://${DOMAIN}/health >/dev/null 2>&1"; then
    ok=1
    break
  fi
  sleep 1
done
if [[ -z $ok ]]; then
  err "https://${DOMAIN}/health 에 응답이 없다"
  hint "앱 로그: ssh ${TARGET} sudo journalctl -u mentoai -n 30"
  hint "Caddy 로그: ssh ${TARGET} sudo journalctl -u caddy -n 30"
  exit 1
fi
ok "헬스체크 통과"

run "systemctl is-active mentoai caddy"
next \
  "앱 열어보기: https://${DOMAIN}  ㅣ  어드민: https://${DOMAIN}/admin" \
  "앱 로그: ssh ${TARGET} sudo journalctl -u mentoai -f" \
  "재배포: 이 명령 다시 실행 (바이너리 교체 + 무중단에 가깝게 재시작)" \
  "데이터 현황: ssh ${TARGET} 'cd /opt/mentoai && sudo ./mentoai status'"

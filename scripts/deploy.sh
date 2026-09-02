#!/usr/bin/env bash
# MentoAI 우분투 원터치 배포: 의존성 확인/설치 → .env 준비 → 빌드 → 기동 → 헬스체크
#
# 사용법:
#   bash scripts/deploy.sh            # sudo 없이 docker를 쓸 수 있으면 그대로 진행
#   sudo bash scripts/deploy.sh       # 최초 1회는 이렇게 (설치 + docker 그룹 등록)
#
# 방화벽(ufw)이 켜져 있으면 80/443(tcp)·443(udp — HTTP/3) 포트를 자동 개방한다.
set -euo pipefail

cd "$(dirname "$0")/.."   # 저장소 루트 기준 실행

log()  { printf '\033[1;36m[mentoai]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[mentoai]\033[0m %s\n' "$*"; }

# --- 시크릿 1차 게이트: 유출 징후가 있으면 배포 중단 ---
log "시크릿 사전 점검"
bash scripts/check-secrets.sh

# --- 권한: docker를 바로 쓸 수 없으면 sudo로 재실행 (apt 설치에도 root 필요) ---
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    log "docker 접근 가능 — 진행한다"
  else
    log "docker 사용에 sudo가 필요하다 — sudo로 재실행한다"
    exec sudo -E bash "$0" "$@"
  fi
fi

# --- 의존성: 없으면 설치 스크립트 호출 ---
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  log "Docker/Compose가 없다 — setup-ubuntu.sh로 설치한다"
  bash "$(dirname "$0")/setup-ubuntu.sh"
else
  log "docker $(docker --version | awk '{print $3}' | tr -d ',') / compose $(docker compose version --short) 확인"
fi

# docker 그룹 등록 (재로그인 후 sudo 없이 사용)
if [[ -n ${SUDO_USER:-} ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
  usermod -aG docker "$SUDO_USER" 2>/dev/null || true
  warn "${SUDO_USER} 사용자를 docker 그룹에 추가했다 — 재로그인하면 sudo 없이 docker를 쓸 수 있다"
fi

# --- .env 준비: 없으면 예시에서 생성 + AUTH_SECRET 자동 발급 ---
if [[ ! -f .env ]]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    {
      printf '\n# 로그인 세션 서명 키 (자동 생성 — 구글/토스 로그인 사용 시 필요)\n'
      printf 'AUTH_SECRET=%s\n' "$(openssl rand -hex 32)"
    } >> .env
  fi
  chown "${SUDO_USER:-$(id -un)}" .env 2>/dev/null || true
  warn ".env를 새로 만들었다 — 공고 수집·임베딩을 쓰려면 GOOGLE_API_KEY를 채우고 다음을 실행:"
  warn "  docker compose up -d   (env 재적용)"
else
  log ".env 확인"
fi

# --- 방화벽: ufw 활성 시 HTTP/3까지 열기 ---
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  log "ufw에 80/tcp·443/tcp·443/udp(HTTP/3) 개방"
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw allow 443/udp >/dev/null
fi

# --- 빌드 & 기동 (마이그레이션·시드·스케줄러는 serve가 자동 처리) ---
log "빌드 및 기동: docker compose up -d --build"
docker compose up -d --build

# --- 헬스체크: 443이 응답할 때까지 대기 (최대 90초) ---
DOMAIN=$(grep -E '^CADDY_DOMAIN=' .env 2>/dev/null | cut -d= -f2- | tr -d '\"'"'"' ' || true)
DOMAIN=${DOMAIN:-localhost}
log "헬스체크 대기: https://${DOMAIN} ..."
ok=""
for _ in $(seq 1 90); do
  # --resolve로 서버 로컬에서도 도메인 SNI 그대로 검사한다
  if curl -skf --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ -z $ok ]]; then
  warn "헬스체크 실패 — 최근 로그:"
  docker compose logs --tail=30
  exit 1
fi

log "배포 완료!"
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
echo ""
echo "  앱:     https://${DOMAIN}"
echo "  어드민: https://${DOMAIN}/admin"
echo ""
echo "  로그:      make logs ㅣ make logs-caddy"
echo "  중단:      make down"
echo "  재배포:    bash scripts/deploy.sh (또는 make deploy)"
[[ -f .env ]] && grep -q '^GOOGLE_API_KEY=$' .env 2>/dev/null && \
  warn "GOOGLE_API_KEY가 비어 있다 — 공고 수집/임베딩을 쓰려면 .env에 입력 후 'docker compose up -d'"
exit 0

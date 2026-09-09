#!/usr/bin/env bash
# MentoAI 우분투 원터치 배포: 의존성 확인/설치 → .env 준비 → 빌드 → 기동 → 헬스체크
#
# 사용법:
#   bash scripts/deploy.sh            # sudo 없이 docker를 쓸 수 있으면 그대로 진행
#   sudo bash scripts/deploy.sh       # 최초 1회는 이렇게 (설치 + docker 그룹 등록)
#
# 방화벽(ufw)이 켜져 있으면 80/443(tcp)·443(udp — HTTP/3) 포트를 자동 개방한다.
set -euo pipefail

cd "$(dirname "$0")/.." || exit 1
# shellcheck source=scripts/lib.sh
source scripts/lib.sh
# shellcheck disable=SC2034  # lib.sh step()에서 사용
STEP_TOTAL=6
title "Docker 배포 (로컬/컨테이너 환경)"

# --- [1/6] 시크릿 1차 게이트 ---
step "시크릿 사전 검사"
bash scripts/check-secrets.sh

# --- [2/6] Docker 확인 ---
step "Docker 확인"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  ok "docker 접근 가능 ($(docker --version | sed 's/,//' | awk '{print $3}'))"
else
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    warn "docker를 바로 쓸 수 없다 — sudo로 다시 실행한다"
    exec sudo -E bash "$0" "$@"
  fi
  err "Docker가 없거나 실행 중이 아니다"
  hint "이 스크립트가 설치를 시도합니다: sudo bash scripts/setup-ubuntu.sh"
  hint "macOS라면 Docker Desktop을 실행한 뒤 다시 시도하세요"
  exit 1
fi

# --- [3/6] docker 그룹 등록 (재로그인 후 sudo 없이 사용) ---
if [[ -n ${SUDO_USER:-} ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
  usermod -aG docker "$SUDO_USER" 2>/dev/null || true
  warn "$SUDO_USER 사용자를 docker 그룹에 추가했다 — 재로그인하면 sudo 없이 docker를 쓸 수 있다"
else
  skip "docker 그룹 설정 (이미 완료)"
fi

# --- [4/6] .env 준비 ---
step ".env 확인"
if [[ ! -f .env ]]; then
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    {
      printf '\n# 로그인 세션 서명 키 (자동 생성 — 구글/토스 로그인 사용 시 필요)\n'
      printf 'AUTH_SECRET=%s\n' "$(openssl rand -hex 32)"
    } >> .env
  fi
  chown "${SUDO_USER:-$(id -un)}" .env 2>/dev/null || true
  ok ".env를 새로 만들었다 (AUTH_SECRET 자동 발급 포함)"
  warn "GOOGLE_API_KEY 등 필요한 값을 채우려면: nano .env → 저장 후 'docker compose up -d'"
else
  ok ".env 확인"
fi

# --- [5/6] 방화벽 (ufw 활성 시에만) ---
step "방화벽 확인"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp  >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw allow 443/udp >/dev/null
  ok "ufw에 80/tcp·443/tcp·443/udp(HTTP/3) 개방"
else
  skip "ufw 비활성 (클라우드라면 보안그룹/방화벽에서 80·443을 열었는지 확인)"
fi

# --- [6/6] 빌드·기동 + 헬스체크 ---
step "빌드 및 기동 (docker compose up -d --build)"
docker compose up -d --build

step "헬스체크 (최대 90초)"
DOMAIN=$(grep -E '^CADDY_DOMAIN=' .env 2>/dev/null | cut -d= -f2- | tr -d ' "'"'"'' || true)
DOMAIN=${DOMAIN:-localhost}
ok=""
for _ in $(seq 1 90); do
  if curl -skf --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ -z $ok ]]; then
  err "https://${DOMAIN}/health 에 응답이 없다"
  hint "로그 확인: make logs ㅣ make logs-caddy"
  hint "처음이라면 1~2분 후 다시 시도해도 된다 (이미지 빌드가 느릴 수 있다)"
  docker compose logs --tail=20
  exit 1
fi
ok "헬스체크 통과"

docker compose ps --format 'table {{.Name}}\t{{.Status}}'
next \
  "앱 열어보기: https://${DOMAIN}  ㅣ  어드민: https://${DOMAIN}/admin" \
  "공고 수집: make pipeline  (GOOGLE_API_KEY 필요)" \
  "로그 보기: make logs ㅣ make logs-caddy  ㅣ  중단: make down"

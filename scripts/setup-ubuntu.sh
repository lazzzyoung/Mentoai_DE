#!/usr/bin/env bash
# MentoAI 우분투 의존성 설치: Docker Engine + Compose 플러그인 (+ 선택적으로 Go 툴체인)
#
# 사용법:
#   sudo bash scripts/setup-ubuntu.sh              # Docker 스택만
#   sudo bash scripts/setup-ubuntu.sh --with-go    # 로컬 테스트/CLI용 Go도 설치
#
# - Docker는 공식 리포지터리(docker.com)에서 설치한다 (apt docker.io보다 최신).
# - Go는 go.mod 버전(1.27)에 맞춰 공식 tarball로 설치한다 (GO_VERSION=1.27.x 로 override 가능).
set -euo pipefail

log()  { printf '\033[1;36m[mentoai-setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[mentoai-setup]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[mentoai-setup]\033[0m %s\n' "$*" >&2; exit 1; }

[[ ${EUID:-$(id -u)} -eq 0 ]] || die "root 권한이 필요하다 — sudo bash scripts/setup-ubuntu.sh"

# --- 우분투 확인 ---
# shellcheck source=/dev/null
. /etc/os-release
if [[ ${ID:-} != ubuntu ]]; then
  warn "이 스크립트는 우분투 기준이다 (감지된 OS: ${ID:-unknown}) — 계속하지만 검증되지 않았다"
fi
CODENAME=${VERSION_CODENAME:-$(lsb_release -cs 2>/dev/null || true)}
[[ -n $CODENAME ]] || die "우분투 코드명을 알 수 없다 (VERSION_CODENAME/lsb_release)"
ARCH=$(dpkg --print-architecture)
log "대상: ubuntu ${VERSION_ID:-?} ${CODENAME} (${ARCH})"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git make lsb-release >/dev/null
log "기본 패키지 설치 완료 (curl/git/make)"

# --- Docker Engine + Compose 플러그인 (공식 리포지터리) ---
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  log "Docker 이미 설치됨: $(docker --version | sed 's/,//')"
else
  log "충돌 가능한 구버전 패키지 제거 (컨테이너/볼륨 데이터는 유지된다)"
  for p in docker.io docker-doc docker-compose podman-docker containerd runc; do
    apt-get remove -y "$p" >/dev/null 2>&1 || true
  done

  log "Docker 공식 apt 리포지터리 등록 (${CODENAME})"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq

  log "Docker Engine + Buildx + Compose 플러그인 설치"
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi

# systemd 환경(실서버)에서만 서비스 활성화 — 컨테이너 안 실행은 무시한다
if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
  systemctl enable --now docker
  log "docker 서비스 활성화 완료"
fi

# docker 그룹: 재로그인 후 sudo 없이 docker 사용 가능
getent group docker >/dev/null || groupadd docker
if [[ -n ${SUDO_USER:-} ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
  usermod -aG docker "$SUDO_USER"
  warn "${SUDO_USER} 사용자를 docker 그룹에 추가했다 — 재로그인 후 적용된다"
fi

# --- 선택: Go 툴체인 (로컬 테스트/CLI 빌드용 — Docker 배포에는 불필요) ---
if [[ ${1:-} == "--with-go" ]]; then
  GO_VERSION=${GO_VERSION:-1.27.0}
  if command -v go >/dev/null 2>&1 && go version | grep -q "go${GO_VERSION}"; then
    log "Go 이미 설치됨: $(go version)"
  else
    log "Go ${GO_VERSION} (linux-${ARCH}) 설치"
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${ARCH}.tar.gz" -o /tmp/mentoai-go.tgz
    rm -rf /usr/local/go
    tar -C /usr/local -xzf /tmp/mentoai-go.tgz
    rm -f /tmp/mentoai-go.tgz
    ln -sf /usr/local/go/bin/go /usr/local/bin/go
    ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt
    log "설치됨: $(/usr/local/go/bin/go version)"
  fi
fi

log "완료. 다음: bash scripts/deploy.sh  (빌드 + 기동 + 헬스체크까지 원터치)"

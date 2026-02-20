#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash setup_ubuntu.sh
# What it does:
#   - Create & persist 16GB swapfile (+ swappiness=10)
#   - Install uv
#   - Ensure Python 3.12
#   - Install Docker (official repo) + add current user to docker group
#   - Install certbot (Let's Encrypt)
# Notes:
#   - Idempotent: 여러 번 실행해도 안전하도록 구성
#   - Ubuntu 시스템 python3 링크는 distro 기본(예: 24.04=3.12) 유지

log() { echo -e "\n==> $*"; }

ensure_system_python3() {
  # 과거 스크립트로 /usr/bin/python3가 3.11로 바뀐 경우 복구
  # (apt/certbot 등 Ubuntu 시스템 도구 안정성 확보)
  if [[ -x /usr/bin/python3.12 ]]; then
    current_target="$(readlink -f /usr/bin/python3 2>/dev/null || true)"
    if [[ "$current_target" != "/usr/bin/python3.12" ]]; then
      log "Restoring /usr/bin/python3 -> /usr/bin/python3.12 for system tools"
      sudo ln -sf /usr/bin/python3.12 /usr/bin/python3
    fi
  fi
}

# -----------------------------
# 1) 16GB swap (create + persist)
# -----------------------------
setup_swap() {
  log "Setting up 16GB swap (/swapfile)..."

  if swapon --show | awk '{print $1}' | grep -qx "/swapfile"; then
    echo "Swapfile already active: /swapfile"
  else
    if [ -f /swapfile ]; then
      echo "/swapfile exists but not active. Re-initializing..."
    else
      echo "Creating /swapfile (16GB)..."
      sudo fallocate -l 16G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=16384 status=progress
    fi

    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
  fi

  # Persist in fstab if not already present
  if ! grep -qE '^\s*/swapfile\s+none\s+swap\s+' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi

  # Swappiness
  if ! grep -qE '^\s*vm\.swappiness\s*=' /etc/sysctl.conf; then
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf >/dev/null
  else
    # Replace existing swappiness line
    sudo sed -i 's/^\s*vm\.swappiness\s*=.*/vm.swappiness=10/' /etc/sysctl.conf
  fi
  sudo sysctl -p >/dev/null

  log "Swap status"
  free -h
  swapon --show || true
}

# -----------------------------
# 2) Install uv (Astral)
# -----------------------------
install_uv() {
  log "Installing uv..."
  if command -v uv >/dev/null 2>&1; then
    echo "uv already installed: $(uv --version)"
    return
  fi

  curl -LsSf https://astral.sh/uv/install.sh | sh

  # uv typically installs to ~/.local/bin
  export PATH="$HOME/.local/bin:$PATH"

  if ! command -v uv >/dev/null 2>&1; then
    echo "uv installed but not on PATH in this session."
    echo "Add to your shell profile: export PATH=\"$HOME/.local/bin:\$PATH\""
  else
    echo "uv installed: $(uv --version)"
  fi
}

# -----------------------------
# 3) Ensure Python 3.12
# -----------------------------
install_python312() {
  log "Ensuring Python 3.12..."
  if command -v python3.12 >/dev/null 2>&1; then
    echo "python3.12 already installed: $(python3.12 --version)"
  else
    sudo apt update
    sudo apt install -y python3.12 python3.12-venv python3.12-dev
  fi

  # 중요: Ubuntu 시스템 기본 python3(예: 24.04는 3.12)를 건드리지 않습니다.
  # /usr/bin/python3를 임의 변경하면 apt/certbot 등 시스템 도구가 깨질 수 있습니다.

  log "Python versions"
  python3.12 --version || true
  python3 --version || true
}

# -----------------------------
# 4) Install Docker (official)
# -----------------------------
install_docker() {
  log "Installing Docker (official repo)..."

  # 이미 정상 설치되어 있으면 재설치하지 않고 상태만 보강
  if command -v docker >/dev/null 2>&1 && docker --version >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "Docker already installed: $(docker --version)"
    sudo systemctl enable docker >/dev/null 2>&1 || true
    sudo systemctl start docker >/dev/null 2>&1 || true
  else
    sudo apt update
    sudo apt install -y ca-certificates curl gnupg

    sudo install -m 0755 -d /etc/apt/keyrings
    if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
      sudo chmod a+r /etc/apt/keyrings/docker.gpg
    fi

    docker_repo_line="deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable"
    if [[ ! -f /etc/apt/sources.list.d/docker.list ]] || ! grep -q "download.docker.com/linux/ubuntu" /etc/apt/sources.list.d/docker.list; then
      echo "$docker_repo_line" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    fi

    # 오래된 docker.io 계열이 있는 경우만 제거(반복 실행 안전)
    if dpkg -l 2>/dev/null | grep -qE '^ii\s+docker\.io\s'; then
      sudo apt remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null || true
    fi

    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    sudo systemctl enable docker
    sudo systemctl start docker
  fi

  # Add current user to docker group
  if groups "$USER" | grep -q '\bdocker\b'; then
    echo "User '$USER' already in docker group."
  else
    sudo usermod -aG docker "$USER"
    echo "Added '$USER' to docker group. You may need to log out and back in."
  fi

  log "Docker status"
  docker --version || true
  sudo docker --version || true

  # Try running docker as current user (may fail until re-login)
  if docker info >/dev/null 2>&1; then
    echo "Docker usable as current user."
    docker run --rm hello-world >/dev/null 2>&1 && echo "hello-world OK" || true
  else
    echo "Docker not yet usable as current user (likely needs re-login)."
    echo "You can run: newgrp docker  (or log out/in) then retry: docker info"
  fi
}

# -----------------------------
# 5) Install certbot
# -----------------------------
install_certbot() {
  log "Installing certbot..."
  if command -v certbot >/dev/null 2>&1 && certbot --version >/dev/null 2>&1; then
    echo "certbot already installed: $(certbot --version)"
    return
  fi

  sudo apt update
  sudo apt install -y certbot python3-josepy python3-acme

  if certbot --version >/dev/null 2>&1; then
    echo "certbot installed: $(certbot --version)"
    return
  fi

  echo "apt certbot 실행이 불안정하여 snap certbot으로 대체 설치합니다."
  sudo apt install -y snapd
  sudo snap install core
  sudo snap refresh core
  if ! sudo snap list certbot >/dev/null 2>&1; then
    sudo snap install --classic certbot
  fi
  sudo ln -sf /snap/bin/certbot /usr/bin/certbot
  echo "certbot installed via snap: $(certbot --version)"
}

main() {
  log "Starting Ubuntu setup (swap + uv + python3.12 + docker + certbot)"
  ensure_system_python3
  setup_swap
  install_uv
  install_python312
  install_docker
  install_certbot
  log "Done."
}

main "$@"

#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash setup_ubuntu.sh
# What it does:
#   - Create & persist 8GB swapfile (+ swappiness=10)
#   - Install uv
#   - Ensure Python 3.12 + sqlite3 tools
#   - Install certbot
# Notes:
#   - Idempotent: 여러 번 실행해도 안전하도록 구성

log() { echo -e "\n==> $*"; }

setup_swap() {
  log "Setting up 8GB swap (/swapfile)..."

  if swapon --show | awk '{print $1}' | grep -qx "/swapfile"; then
    echo "Swapfile already active: /swapfile"
  else
    if [ ! -f /swapfile ]; then
      sudo fallocate -l 8G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=8192 status=progress
    fi
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
  fi

  if ! grep -qE '^\s*/swapfile\s+none\s+swap\s+' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi

  if ! grep -qE '^\s*vm\.swappiness\s*=' /etc/sysctl.conf; then
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf >/dev/null
  else
    sudo sed -i 's/^\s*vm\.swappiness\s*=.*/vm.swappiness=10/' /etc/sysctl.conf
  fi

  sudo sysctl -p >/dev/null
}

install_uv() {
  log "Installing uv..."
  if command -v uv >/dev/null 2>&1; then
    echo "uv already installed: $(uv --version)"
    return
  fi

  curl -LsSf https://astral.sh/uv/install.sh | sh
  echo "uv 설치 완료. PATH에 ~/.local/bin 추가가 필요할 수 있습니다."
}

install_python() {
  log "Ensuring Python 3.12 + sqlite3 tools..."
  sudo apt update
  sudo apt install -y python3.12 python3.12-venv python3.12-dev sqlite3
  python3 --version || true
  sqlite3 --version || true
}

install_certbot() {
  log "Installing certbot..."
  sudo apt update
  sudo apt install -y certbot
  certbot --version || true
}

main() {
  log "Starting Ubuntu setup (swap + uv + python3.12 + sqlite3 + certbot)"
  setup_swap
  install_uv
  install_python
  install_certbot
  log "Done."
}

main "$@"

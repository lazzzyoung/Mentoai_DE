#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash setup_ubuntu.sh
# What it does:
#   - Create & persist 16GB swapfile (+ swappiness=10)
#   - Install uv
#   - Install Python 3.11 (deadsnakes PPA)
#   - Install Docker (official repo) + add current user to docker group

log() { echo -e "\n==> $*"; }

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
# 3) Install Python 3.11 (deadsnakes)
# -----------------------------
install_python311() {
  log "Installing Python 3.11..."
  if command -v python3.11 >/dev/null 2>&1; then
    echo "python3.11 already installed: $(python3.11 --version)"
  else
    sudo apt update
    sudo apt install -y software-properties-common
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-dev
  fi

  # Optional: set python3 alternative to python3.11 (safe if you want)
  if update-alternatives --query python3 >/dev/null 2>&1; then
    :
  else
    sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
  fi

  log "Python versions"
  python3.11 --version
  python3 --version || true
}

# -----------------------------
# 4) Install Docker (official)
# -----------------------------
install_docker() {
  log "Installing Docker (official repo)..."

  # Remove older packages if present
  sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

  sudo apt update
  sudo apt install -y ca-certificates curl gnupg

  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  sudo apt update
  sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  sudo systemctl enable docker
  sudo systemctl start docker

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

main() {
  log "Starting Ubuntu setup (swap + uv + python3.11 + docker)"
  setup_swap
  install_uv
  install_python311
  install_docker
  log "Done."
}

main "$@"

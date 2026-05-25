#!/usr/bin/env bash
# Configure /etc/docker/daemon.json (log rotation, live-restore).
# Run as root or via sudo:
#   sudo bash scripts/configure-docker-daemon.sh

set -euo pipefail

configure_docker_daemon() {
  echo "Configuring Docker daemon defaults..."
  sudo mkdir -p /etc/docker

  if ! command -v jq >/dev/null 2>&1; then
    echo "jq not found. Installing jq..."
    sudo apt-get update
    sudo apt-get install -y jq
  fi

  local daemon_file="/etc/docker/daemon.json"
  local tmp_file
  tmp_file="$(mktemp)"

  if [ -f "$daemon_file" ]; then
    echo "Existing Docker daemon.json found. Creating backup..."
    sudo cp "$daemon_file" "${daemon_file}.bak.$(date +%Y%m%d-%H%M%S)"

    if ! sudo jq empty "$daemon_file" >/dev/null 2>&1; then
      echo "ERROR: Existing $daemon_file is invalid JSON."
      echo "Fix it manually before continuing."
      rm -f "$tmp_file"
      exit 1
    fi

    sudo jq '
      .["log-driver"] = "json-file" |
      .["log-opts"] = {
        "max-size": "10m",
        "max-file": "3"
      } |
      .["live-restore"] = true
    ' "$daemon_file" > "$tmp_file"
  else
    cat > "$tmp_file" <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true
}
EOF
  fi

  if ! jq empty "$tmp_file" >/dev/null 2>&1; then
    echo "ERROR: Generated daemon.json is invalid JSON."
    rm -f "$tmp_file"
    exit 1
  fi

  if [ -f "$daemon_file" ] && sudo cmp -s "$tmp_file" "$daemon_file"; then
    echo "Docker daemon.json already correct. No restart needed."
    rm -f "$tmp_file"
    return 0
  fi

  echo "Writing updated Docker daemon config..."
  sudo install -m 0644 "$tmp_file" "$daemon_file"
  rm -f "$tmp_file"

  echo "Restarting Docker..."
  sudo systemctl daemon-reload
  sudo systemctl restart docker
  echo "Docker daemon config applied."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  configure_docker_daemon
fi

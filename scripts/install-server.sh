#!/usr/bin/env bash
# Debian VPS bootstrap — run as root:
#   sudo bash scripts/install-server.sh
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-joe}"
COMPOSE_HOME="${COMPOSE_HOME:-/home/${DEPLOY_USER}/docker-vps-stack}"
APPDATA_ROOT="${APPDATA_ROOT:-/opt/appdata/docker-apps}"

if [[ -f /etc/os-release ]]; then
  # shellcheck source=/dev/null
  . /etc/os-release
  if [[ "${ID}" != "debian" && "${ID_LIKE}" != *debian* ]]; then
    echo "Warning: this script targets Debian; detected ID=${ID:-unknown}"
  fi
fi

echo "==> Installing Docker (if missing)..."
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  DEB_CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-bookworm}")"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${DEB_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "==> Installing cloudflared (for tunnel setup during setup.py)..."
if ! command -v cloudflared >/dev/null 2>&1; then
  apt-get update
  apt-get install -y curl gnupg
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    > /etc/apt/sources.list.d/cloudflared.list
  apt-get update
  apt-get install -y cloudflared
fi

echo "==> Ensuring deploy user ${DEPLOY_USER}..."
if ! id "${DEPLOY_USER}" &>/dev/null; then
  useradd -m -s /bin/bash "${DEPLOY_USER}"
  usermod -aG sudo "${DEPLOY_USER}"
  echo "Created user ${DEPLOY_USER} — set a password: passwd ${DEPLOY_USER}"
fi
usermod -aG docker "${DEPLOY_USER}" 2>/dev/null || true

echo "==> Creating appdata layout..."
mkdir -p "${APPDATA_ROOT}"/{traefik/{dynamic,logs},authelia,portainer/data,postgres/{data,init},redis/data,traefik-manager/{config,backups},rocketchat/mongodb,cloudflared}
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${APPDATA_ROOT}"

if [[ -d "${COMPOSE_HOME}" ]]; then
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${COMPOSE_HOME}"
else
  echo "Clone or copy docker-vps-stack to ${COMPOSE_HOME} before running setup.py"
fi

echo "==> Python for setup.py..."
apt-get install -y python3 python3-pip python3-venv 2>/dev/null || true

echo ""
echo "Done. Run setup as ${DEPLOY_USER} (not root):"
echo "  sudo -u ${DEPLOY_USER} -H bash -lc 'cd ${COMPOSE_HOME} && pip3 install --user -r scripts/requirements.txt && python3 scripts/setup.py'"
echo ""
echo "Mail-in-a-Box: this stack publishes NO host ports; ingress is Cloudflare Tunnel only."

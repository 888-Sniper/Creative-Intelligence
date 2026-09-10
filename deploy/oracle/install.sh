#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="creative-intel"
APP_GROUP="creative-intel"
APP_DIR="/opt/creative-intelligence"
DATA_DIR="/var/lib/creative-intelligence"
ENV_DIR="/etc/creative-intelligence"
SERVICE_NAME="creative-intelligence"
SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DOMAIN="${DOMAIN:-_}"
PNPM_VERSION="${PNPM_VERSION:-10.14.0}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo: sudo DOMAIN=your.domain bash deploy/oracle/install.sh" >&2
  exit 1
fi

if [[ ! -f "${SOURCE_DIR}/pyproject.toml" ]]; then
  echo "SOURCE_DIR does not look like the Creative Intelligence repository: ${SOURCE_DIR}" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg nginx certbot python3-certbot-nginx \
  ffmpeg build-essential software-properties-common rsync sqlite3 \
  ufw fail2ban unattended-upgrades

# Creative Intelligence currently requires Python >=3.13.
if ! command -v python3.13 >/dev/null 2>&1; then
  add-apt-repository -y ppa:deadsnakes/ppa
  apt-get update
  apt-get install -y --no-install-recommends python3.13 python3.13-venv python3.13-dev
fi

# Node 22 LTS is used to build the Vite/React frontend on ARM64 as well as x86_64.
if ! command -v node >/dev/null 2>&1 || [[ "$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)" -lt 22 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi
if ! command -v corepack >/dev/null 2>&1; then
  npm install --global corepack
fi
corepack enable
corepack prepare "pnpm@${PNPM_VERSION}" --activate

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}" "${DATA_DIR}/media" "${ENV_DIR}"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude 'dist/' \
  --exclude 'Data/' \
  "${SOURCE_DIR}/" "${APP_DIR}/"
chmod 750 "${APP_DIR}/deploy/oracle/"*.sh

python3.13 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip wheel
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.lock"
"${APP_DIR}/.venv/bin/pip" install --no-deps "${APP_DIR}"

pushd "${APP_DIR}/apps/creative-intelligence-ui" >/dev/null
pnpm install --frozen-lockfile
pnpm build
popd >/dev/null

if [[ ! -f "${ENV_DIR}/creative-intelligence.env" ]]; then
  cp "${APP_DIR}/deploy/oracle/env.example" "${ENV_DIR}/creative-intelligence.env"
  chmod 600 "${ENV_DIR}/creative-intelligence.env"
  echo "Created ${ENV_DIR}/creative-intelligence.env — add real WorkOS/admin values before external login testing."
fi

# Apply the production migration chain to the persistent database before first boot.
pushd "${APP_DIR}" >/dev/null
CREATIVE_INTEL_DB_URL="sqlite:////var/lib/creative-intelligence/creative_intel.db" \
  "${APP_DIR}/.venv/bin/alembic" -c Backend/alembic.ini upgrade head
popd >/dev/null

cp "${APP_DIR}/deploy/oracle/creative-intelligence.service" "/etc/systemd/system/${SERVICE_NAME}.service"
cp "${APP_DIR}/deploy/oracle/creative-intelligence-backup.service" "/etc/systemd/system/${SERVICE_NAME}-backup.service"
cp "${APP_DIR}/deploy/oracle/creative-intelligence-backup.timer" "/etc/systemd/system/${SERVICE_NAME}-backup.timer"
cp "${APP_DIR}/deploy/oracle/creative-intelligence-duckdns.service" "/etc/systemd/system/${SERVICE_NAME}-duckdns.service"
cp "${APP_DIR}/deploy/oracle/creative-intelligence-duckdns.timer" "/etc/systemd/system/${SERVICE_NAME}-duckdns.timer"
if [[ ! -f "${ENV_DIR}/duckdns.env" ]]; then
  cp "${APP_DIR}/deploy/oracle/duckdns.env.example" "${ENV_DIR}/duckdns.env"
  chmod 600 "${ENV_DIR}/duckdns.env"
fi
sed "s/__DOMAIN__/${DOMAIN}/g" "${APP_DIR}/deploy/oracle/nginx.conf.template" \
  > "/etc/nginx/sites-available/${SERVICE_NAME}"
ln -sfn "/etc/nginx/sites-available/${SERVICE_NAME}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
rm -f /etc/nginx/sites-enabled/default

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}" "${DATA_DIR}"
chmod 750 "${DATA_DIR}" "${DATA_DIR}/media"

nginx -t
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"
systemctl enable --now "${SERVICE_NAME}-backup.timer"
if grep -q "^DUCKDNS_TOKEN=.\+" "${ENV_DIR}/duckdns.env" 2>/dev/null; then
  systemctl enable --now "${SERVICE_NAME}-duckdns.timer"
else
  echo "DuckDNS token not set: fill ${ENV_DIR}/duckdns.env, then run"
  echo "  sudo systemctl enable --now ${SERVICE_NAME}-duckdns.timer"
fi

# Backup landing zone: the timer runs as creative-intel, so the
# directory must exist with service-account ownership BEFORE the
# timer is enabled (backup.sh cannot create it under /var/backups
# as an unprivileged user).
BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"
mkdir -p "${BACKUP_DIR}"
chown creative-intel:creative-intel "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

# Host firewall: SSH first (never lock out the current session), then
# web ports. Port 4321 stays loopback-only (see nginx template).
if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
fi
if command -v fail2ban-client >/dev/null 2>&1; then
  systemctl enable --now fail2ban
fi
if [[ ! -f /etc/apt/apt.conf.d/20auto-upgrades ]]; then
  cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
fi
systemctl enable nginx
systemctl restart nginx

sleep 2
if ! curl -fsS http://127.0.0.1:4321/health >/dev/null; then
  echo "Application health check failed. Inspect: journalctl -u ${SERVICE_NAME} -n 100 --no-pager" >&2
  exit 1
fi
if ! curl -fsS http://127.0.0.1:4321/readiness >/dev/null; then
  echo "Application readiness check failed. Inspect: journalctl -u ${SERVICE_NAME} -n 100 --no-pager" >&2
  exit 1
fi

echo
if [[ "${DOMAIN}" == "_" ]]; then
  echo "Installed successfully. Open http://<OCI_PUBLIC_IP>/ for the initial network check."
  echo "Before testing WorkOS externally, point a domain at this VM, rerun with DOMAIN=host, then run enable-https.sh."
else
  echo "Installed successfully for http://${DOMAIN}."
  echo "Next: sudo EMAIL=you@example.com DOMAIN=${DOMAIN} bash ${APP_DIR}/deploy/oracle/enable-https.sh"
fi

#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/creative-intelligence"
SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

"${APP_DIR}/deploy/oracle/backup.sh"

rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude 'dist/' \
  --exclude 'Data/' \
  "${SOURCE_DIR}/" "${APP_DIR}/"

"${APP_DIR}/.venv/bin/pip" install --upgrade --force-reinstall "${APP_DIR}"
pushd "${APP_DIR}/apps/creative-intelligence-ui" >/dev/null
corepack enable
pnpm install --frozen-lockfile
pnpm build
popd >/dev/null

pushd "${APP_DIR}" >/dev/null
CREATIVE_INTEL_DB_URL="sqlite:////var/lib/creative-intelligence/creative_intel.db" \
  "${APP_DIR}/.venv/bin/alembic" -c Backend/alembic.ini upgrade head
popd >/dev/null

chown -R creative-intel:creative-intel "${APP_DIR}"
systemctl restart creative-intelligence
sleep 2
curl -fsS http://127.0.0.1:4321/health >/dev/null
curl -fsS http://127.0.0.1:4321/readiness >/dev/null
echo "Creative Intelligence updated successfully."

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
# A18: rsync preserves the source tree's modes, so helpers synced from
# a checkout/export without exec bits would go dead after an update.
# Re-assert modes on every update (install.sh does the same at
# install time); the bits are also committed in git as backup.
# A13: 755 (not 750) so the unprivileged DuckDNS unit can execute them.
chmod 755 "${APP_DIR}/deploy/oracle/"*.sh

"${APP_DIR}/.venv/bin/pip" install --require-hashes -r "${APP_DIR}/requirements.lock"
"${APP_DIR}/.venv/bin/pip" install --upgrade --force-reinstall --no-deps "${APP_DIR}"
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
# A13: deployment helpers stay root-owned and non-writable by the
# application account (see install.sh) — re-applied after every pull.
chown -R root:root "${APP_DIR}/deploy"
chmod 755 "${APP_DIR}/deploy" "${APP_DIR}/deploy/oracle"
# 755 (not 750): the unprivileged DuckDNS unit must still be able to
# read and execute the updater; no secrets live in these files.
chmod 755 "${APP_DIR}/deploy/oracle/"*.sh
for unit in creative-intelligence.service creative-intelligence-backup.service \
            creative-intelligence-backup.timer creative-intelligence-duckdns.service \
            creative-intelligence-duckdns.timer creative-intelligence-worker.service; do
  cp "${APP_DIR}/deploy/oracle/${unit}" "/etc/systemd/system/${unit}"
done
systemctl daemon-reload
systemctl restart creative-intelligence
systemctl try-restart creative-intelligence-worker
sleep 2
curl -fsS http://127.0.0.1:4321/health >/dev/null
curl -fsS http://127.0.0.1:4321/readiness >/dev/null
echo "Creative Intelligence updated successfully."

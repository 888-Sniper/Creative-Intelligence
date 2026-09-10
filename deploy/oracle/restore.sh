#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE="${1:-}"
DATA_DIR="${CREATIVE_INTEL_DATA_DIR:-/var/lib/creative-intelligence}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
if [[ -z "${ARCHIVE}" || ! -f "${ARCHIVE}" ]]; then
  echo "Usage: sudo deploy/oracle/restore.sh /var/backups/creative-intelligence/<backup>.tar.gz" >&2
  exit 1
fi

systemctl stop creative-intelligence
tar -xzf "${ARCHIVE}" -C "${TMP}"
ROOT="$(find "${TMP}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "${ROOT}" || ! -f "${ROOT}/creative_intel.db" ]]; then
  echo "Backup does not contain creative_intel.db" >&2
  exit 1
fi

mkdir -p "${DATA_DIR}"
cp "${ROOT}/creative_intel.db" "${DATA_DIR}/creative_intel.db"
rm -rf "${DATA_DIR}/media" "${DATA_DIR}/avatars"
[[ -d "${ROOT}/media" ]] && cp -a "${ROOT}/media" "${DATA_DIR}/media"
[[ -d "${ROOT}/avatars" ]] && cp -a "${ROOT}/avatars" "${DATA_DIR}/avatars"
mkdir -p "${DATA_DIR}/media"
chown -R creative-intel:creative-intel "${DATA_DIR}"
chmod 750 "${DATA_DIR}" "${DATA_DIR}/media"

systemctl start creative-intelligence
sleep 2
curl -fsS http://127.0.0.1:4321/readiness >/dev/null
echo "Restore completed successfully."

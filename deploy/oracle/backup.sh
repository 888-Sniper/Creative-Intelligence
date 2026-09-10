#!/usr/bin/env bash
set -Eeuo pipefail

DATA_DIR="${CREATIVE_INTEL_DATA_DIR:-/var/lib/creative-intelligence}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${STAMP}"
DB="${DATA_DIR}/creative_intel.db"

mkdir -p "${TARGET}"
chmod 700 "${BACKUP_DIR}" "${TARGET}"

if [[ -f "${DB}" ]]; then
  sqlite3 "${DB}" ".backup '${TARGET}/creative_intel.db'"
fi
if [[ -d "${DATA_DIR}/media" ]]; then
  rsync -a "${DATA_DIR}/media/" "${TARGET}/media/"
fi
if [[ -d "${DATA_DIR}/avatars" ]]; then
  rsync -a "${DATA_DIR}/avatars/" "${TARGET}/avatars/"
fi

cat > "${TARGET}/MANIFEST.txt" <<MANIFEST
created_utc=${STAMP}
database=${DB}
media_dir=${DATA_DIR}/media
MANIFEST

tar -C "${BACKUP_DIR}" -czf "${BACKUP_DIR}/${STAMP}.tar.gz" "${STAMP}"
rm -rf "${TARGET}"
chmod 600 "${BACKUP_DIR}/${STAMP}.tar.gz"
echo "${BACKUP_DIR}/${STAMP}.tar.gz"

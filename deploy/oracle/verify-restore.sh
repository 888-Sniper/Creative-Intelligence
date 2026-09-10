#!/usr/bin/env bash
# Automated restore test: prove the newest (or given) backup is intact
# and restorable without touching live data. Exits non-zero on any
# failure so the weekly systemd timer surfaces a failed unit.
#
# Usage: verify-restore.sh [path-to-tarball]
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"
TARBALL="${1:-}"

if [[ -z "${TARBALL}" ]]; then
  shopt -s nullglob
  _CANDIDATES=("${BACKUP_DIR}"/*.tar.gz.enc "${BACKUP_DIR}"/*.tar.gz)
  if ((${#_CANDIDATES[@]})); then
    TARBALL="$(ls -t "${_CANDIDATES[@]}" | head -n 1)"
  fi
fi
if [[ -z "${TARBALL}" || ! -f "${TARBALL}" ]]; then
  echo "No backup tarball found in ${BACKUP_DIR}." >&2
  exit 1
fi

if [[ -f "${TARBALL}.sha256" ]]; then
  sha256sum -c "${TARBALL}.sha256" --quiet || {
    echo "Hash mismatch for ${TARBALL}." >&2
    exit 1
  }
else
  echo "WARNING: no sidecar hash for ${TARBALL}; skipping hash check." >&2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

PAYLOAD="${TARBALL}"
if [[ "${TARBALL}" == *.enc ]]; then
  if [[ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
    echo "Encrypted backup but BACKUP_ENCRYPTION_PASSPHRASE is not set." >&2
    exit 1
  fi
  PAYLOAD="${TMP}/backup.tar.gz"
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
    -in "${TARBALL}" -out "${PAYLOAD}" || {
    echo "Decryption failed for ${TARBALL}." >&2
    exit 1
  }
fi

tar -tzf "${PAYLOAD}" | grep -q "/MANIFEST.txt$" || {
  echo "MANIFEST.txt missing from ${TARBALL}." >&2
  exit 1
}
tar -xzf "${PAYLOAD}" -C "${TMP}"
DB="$(find "${TMP}" -name creative_intel.db | head -n 1)"
if [[ -z "${DB}" ]]; then
  echo "creative_intel.db missing from ${TARBALL}." >&2
  exit 1
fi
if [[ "$(sqlite3 "${DB}" "PRAGMA integrity_check;")" != "ok" ]]; then
  echo "SQLite integrity_check failed for ${TARBALL}." >&2
  exit 1
fi

echo "RESTORE_OK ${TARBALL}"

#!/usr/bin/env bash
# Restore Creative Intelligence from a backup.sh archive.
#
# A11 hardening, in strict order:
#   1. Verify + decrypt + stage + validate BEFORE any downtime, using
#      the same checks as verify-restore.sh (sidecar hash, AES-256-CBC
#      decrypt of .tar.gz.enc, MANIFEST.txt, creative_intel.db
#      present, SQLite integrity_check).
#   2. Only then stop ALL writers (web service AND worker).
#   3. Snapshot the live database for rollback, swap in the staged
#      copy (clearing stale -wal/-shm so SQLite never replays the
#      pre-restore journal), sync media/avatars, fix ownership.
#   4. Restart exactly the units that were active; any failure after
#      downtime begins rolls the database back and restores the
#      previous unit states instead of leaving a stopped box.
#
# Usage: sudo deploy/oracle/restore.sh /var/backups/creative-intelligence/<backup>.tar.gz[.enc]
set -Eeuo pipefail

ARCHIVE="${1:-}"
DATA_DIR="${CREATIVE_INTEL_DATA_DIR:-/var/lib/creative-intelligence}"
WEB_UNIT="creative-intelligence.service"
WORKER_UNIT="creative-intelligence-worker.service"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
if [[ -z "${ARCHIVE}" || ! -f "${ARCHIVE}" ]]; then
  echo "Usage: sudo deploy/oracle/restore.sh /var/backups/creative-intelligence/<backup>.tar.gz[.enc]" >&2
  exit 1
fi

# ---- 1. Pre-downtime staging + validation (no services touched) ----
if [[ -f "${ARCHIVE}.sha256" ]]; then
  sha256sum -c "${ARCHIVE}.sha256" --quiet || {
    echo "Hash mismatch for ${ARCHIVE}; refusing to restore." >&2
    exit 1
  }
else
  echo "WARNING: no sidecar hash for ${ARCHIVE}; skipping hash check." >&2
fi

PAYLOAD="${ARCHIVE}"
if [[ "${ARCHIVE}" == *.enc ]]; then
  if [[ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
    echo "Encrypted backup but BACKUP_ENCRYPTION_PASSPHRASE is not set." >&2
    exit 1
  fi
  PAYLOAD="${TMP}/backup.tar.gz"
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
    -in "${ARCHIVE}" -out "${PAYLOAD}" || {
    echo "Decryption failed for ${ARCHIVE}." >&2
    exit 1
  }
fi

tar -tzf "${PAYLOAD}" | grep -q "/MANIFEST.txt$" || {
  echo "MANIFEST.txt missing from ${ARCHIVE}." >&2
  exit 1
}
tar -xzf "${PAYLOAD}" -C "${TMP}"
ROOT="$(find "${TMP}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "${ROOT}" || ! -f "${ROOT}/creative_intel.db" ]]; then
  echo "Backup does not contain creative_intel.db" >&2
  exit 1
fi
if [[ "$(sqlite3 "${ROOT}/creative_intel.db" "PRAGMA integrity_check;")" != "ok" ]]; then
  echo "SQLite integrity_check failed for the staged database." >&2
  exit 1
fi
echo "Staged and validated ${ARCHIVE} with zero downtime so far."

# ---- 2-4. Downtime swap with rollback ----
unit_was_active() {
  systemctl is-active --quiet "$1" 2>/dev/null
}

WEB_WAS_ACTIVE=false
WORKER_WAS_ACTIVE=false
if unit_was_active "${WEB_UNIT}"; then WEB_WAS_ACTIVE=true; fi
if unit_was_active "${WORKER_UNIT}"; then WORKER_WAS_ACTIVE=true; fi
ROLLBACK=""
DOWNTIME=false

rollback() {
  # Best-effort only: we are already failing; never mask the cause.
  if [[ "${DOWNTIME}" == "true" ]]; then
    if [[ -n "${ROLLBACK}" && -f "${ROLLBACK}/creative_intel.db" ]]; then
      cp -f "${ROLLBACK}/creative_intel.db" "${DATA_DIR}/creative_intel.db" || true
      rm -f "${DATA_DIR}/creative_intel.db-wal" "${DATA_DIR}/creative_intel.db-shm" || true
      chown creative-intel:creative-intel "${DATA_DIR}/creative_intel.db" || true
    fi
    [[ "${WORKER_WAS_ACTIVE}" == "true" ]] && systemctl start "${WORKER_UNIT}" || true
    [[ "${WEB_WAS_ACTIVE}" == "true" ]] && systemctl start "${WEB_UNIT}" || true
  fi
  rm -rf "${ROLLBACK}" 2>/dev/null || true
}
# shellcheck disable=SC2154 # rc is assigned by the trap itself at fire time
trap 'rc=$?; rollback; rm -rf "${TMP}"; exit ${rc}' EXIT

# Stop every database writer before replacing the file.
systemctl stop "${WORKER_UNIT}" 2>/dev/null || true
systemctl stop "${WEB_UNIT}" 2>/dev/null || true
DOWNTIME=true

# Snapshot the live database so a failed swap can roll back.
ROLLBACK="$(mktemp -d)"
if [[ -f "${DATA_DIR}/creative_intel.db" ]]; then
  cp -f "${DATA_DIR}/creative_intel.db" "${ROLLBACK}/creative_intel.db"
fi

mkdir -p "${DATA_DIR:?}"
cp -f "${ROOT}/creative_intel.db" "${DATA_DIR:?}/creative_intel.db"
# Never replay the pre-restore journal against the restored copy.
rm -f "${DATA_DIR:?}/creative_intel.db-wal" "${DATA_DIR:?}/creative_intel.db-shm"
rm -rf "${DATA_DIR:?}/media" "${DATA_DIR:?}/avatars"
[[ -d "${ROOT}/media" ]] && cp -a "${ROOT}/media" "${DATA_DIR}/media"
[[ -d "${ROOT}/avatars" ]] && cp -a "${ROOT}/avatars" "${DATA_DIR}/avatars"
mkdir -p "${DATA_DIR}/media"
chown -R creative-intel:creative-intel "${DATA_DIR}"
chmod 750 "${DATA_DIR}" "${DATA_DIR}/media"

# Restart exactly what was running before.
if [[ "${WORKER_WAS_ACTIVE}" == "true" ]]; then systemctl start "${WORKER_UNIT}"; fi
if [[ "${WEB_WAS_ACTIVE}" == "true" ]]; then systemctl start "${WEB_UNIT}"; fi
if [[ "${WEB_WAS_ACTIVE}" == "true" ]]; then
  sleep 2
  curl -fsS http://127.0.0.1:4321/readiness >/dev/null
fi

# Success: no rollback needed.
DOWNTIME=false
trap 'rm -rf "${TMP}" "${ROLLBACK}"' EXIT
rm -rf "${ROLLBACK}"
echo "Restore completed successfully."

#!/usr/bin/env bash
# Nightly Creative Intelligence backup: consistent SQLite copy + media.
#
# Hardening: AES-256-CBC encryption (passphrase only from the
# environment, never the repo), a SHA-256 sidecar verified straight
# after writing, and local retention pruning. Encryption is MANDATORY
# when CREATIVE_INTEL_ENVIRONMENT=production (fail closed, no plaintext
# client data at rest); elsewhere it is strongly recommended. Plaintext
# archives are refused by offhost_backup.sh once a passphrase is
# configured, so client data never leaves the VM unencrypted.
#
#   BACKUP_ENCRYPTION_PASSPHRASE  when set, the tarball is encrypted to
#                                 <stamp>.tar.gz.enc and the plaintext
#                                 is removed (generate: openssl rand -base64 32)
#   BACKUP_KEEP_DAILY             newest on-host archives kept (default 14)
set -Eeuo pipefail

DATA_DIR="${CREATIVE_INTEL_DATA_DIR:-/var/lib/creative-intelligence}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-14}"

if [[ "${CREATIVE_INTEL_ENVIRONMENT:-}" == "production" && -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
  echo "Refusing plaintext backup: BACKUP_ENCRYPTION_PASSPHRASE is required" >&2
  echo "when CREATIVE_INTEL_ENVIRONMENT=production." >&2
  exit 1
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="${BACKUP_DIR}/${STAMP}"
DB="${DATA_DIR}/creative_intel.db"

if [[ -e "${BACKUP_DIR}" && ! -w "${BACKUP_DIR}" ]]; then
  echo "Backup directory ${BACKUP_DIR} is not writable by $(whoami)." >&2
  echo "On Oracle VMs the installer creates it with creative-intel ownership." >&2
  exit 1
fi
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

ENCRYPTED=false
if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]]; then
  ENCRYPTED=true
fi

cat > "${TARGET}/MANIFEST.txt" <<MANIFEST
created_utc=${STAMP}
database=${DB}
media_dir=${DATA_DIR}/media
encrypted=${ENCRYPTED}
MANIFEST

# COPYFILE_DISABLE keeps macOS AppleDouble (._*) files out of archives
# when the scripts ever run on a Mac; GNU tar on Linux ignores it.
COPYFILE_DISABLE=1 tar -C "${BACKUP_DIR}" -czf "${BACKUP_DIR}/${STAMP}.tar.gz" "${STAMP}"
rm -rf "${TARGET}"

ARCHIVE="${BACKUP_DIR}/${STAMP}.tar.gz"
if [[ "${ENCRYPTED}" == "true" ]]; then
  if openssl enc -aes-256-cbc -pbkdf2 \
      -pass env:BACKUP_ENCRYPTION_PASSPHRASE \
      -in "${ARCHIVE}" -out "${ARCHIVE}.enc"; then
    chmod 600 "${ARCHIVE}.enc"
    rm -f "${ARCHIVE}"
    ARCHIVE="${ARCHIVE}.enc"
  else
    rm -f "${ARCHIVE}" "${ARCHIVE}.enc"
    echo "Encryption failed; partial outputs removed." >&2
    exit 1
  fi
else
  chmod 600 "${ARCHIVE}"
  echo "WARNING: BACKUP_ENCRYPTION_PASSPHRASE is not set; archive is unencrypted." >&2
fi

# Integrity hash, verified immediately: a corrupt write fails the run.
sha256sum "${ARCHIVE}" > "${ARCHIVE}.sha256"
chmod 600 "${ARCHIVE}.sha256"
sha256sum -c "${ARCHIVE}.sha256" --quiet

# Local retention: keep the newest KEEP_DAILY archives and their hashes.
shopt -s nullglob
_ARCHIVES=("${BACKUP_DIR}"/*.tar.gz "${BACKUP_DIR}"/*.tar.gz.enc)
if ((${#_ARCHIVES[@]})); then
  ls -t "${_ARCHIVES[@]}" | tail -n "+$((KEEP_DAILY + 1))" \
    | while IFS= read -r OLD; do
    rm -f "${OLD}" "${OLD}.sha256"
  done
fi

echo "${ARCHIVE}"

#!/usr/bin/env bash
# Copy a Creative Intelligence backup tarball to an off-host destination.
# Destination comes only from the environment (systemd EnvironmentFile or
# operator shell) so no host, bucket, or credential ever lands in the repo.
#
# Encryption rule: once BACKUP_ENCRYPTION_PASSPHRASE is configured, only
# *.tar.gz.enc archives may leave the VM — a plaintext tarball is refused
# so client data is never transferred unencrypted. Without a configured
# passphrase, plaintext transfers proceed with a loud warning.
#
#   BACKUP_OFFHOST_DEST   rsync destination, e.g. backup@vault:/srv/ci-backups
#                         or a mounted bucket path. Empty means "not configured".
#   BACKUP_OFFHOST_KEEP   keep this many newest tarballs at a local-path
#                         destination (default 14). Remote pruning is left to
#                         the remote side (e.g. bucket lifecycle rules).
#   BACKUP_DIR            local backup dir (default /var/backups/creative-intelligence)
#
# Usage: offhost_backup.sh [path-to-tarball]
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"
DEST="${BACKUP_OFFHOST_DEST:-}"
KEEP="${BACKUP_OFFHOST_KEEP:-14}"
TARBALL="${1:-}"

if [[ -z "${DEST}" ]]; then
  echo "BACKUP_OFFHOST_DEST is not set; off-host copy skipped (on-host backup is unaffected)." >&2
  exit 0
fi

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

if [[ -n "${BACKUP_ENCRYPTION_PASSPHRASE:-}" && "${TARBALL}" != *.enc ]]; then
  echo "Refusing to transfer unencrypted ${TARBALL} while BACKUP_ENCRYPTION_PASSPHRASE is set." >&2
  exit 1
fi
if [[ "${TARBALL}" != *.enc ]]; then
  echo "WARNING: transferring unencrypted ${TARBALL}; set BACKUP_ENCRYPTION_PASSPHRASE." >&2
fi

rsync -a "${TARBALL}" "${DEST}/"
if [[ -f "${TARBALL}.sha256" ]]; then
  rsync -a "${TARBALL}.sha256" "${DEST}/"
fi

# Prune old tarballs only when the destination is a local path we own.
if [[ "${DEST}" != *:* && -d "${DEST}" ]]; then
  shopt -s nullglob
  _REMOTE=("${DEST}"/*.tar.gz "${DEST}"/*.tar.gz.enc)
  if ((${#_REMOTE[@]})); then
    ls -t "${_REMOTE[@]}" | tail -n "+$((KEEP + 1))" \
      | while IFS= read -r OLD; do
      rm -f "${OLD}" "${OLD}.sha256"
    done
  fi
fi

echo "Off-host backup complete: $(basename "${TARBALL}") -> ${DEST}"

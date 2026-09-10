#!/usr/bin/env bash
# One-command free demo setup for Oracle Always Free + DuckDNS.
# Idempotent: safe to re-run; each step detects existing state.
#
#   sudo DOMAIN=creative-intelligence.duckdns.org EMAIL=admin@example.com \
#     bash deploy/oracle/setup-demo.sh
#
# Optional:
#   DUCKDNS_ENV_FILE  path to duckdns.env (default /etc/creative-intelligence/duckdns.env)
#   SOURCE_DIR        repo checkout (default: this script's repo root)
#   SKIP_DNS_WAIT=1   skip the DNS-propagation wait (sslip.io still verified)
#   SKIP_HTTPS=1      install over HTTP only (not for public demos)
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${SOURCE_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
APP_DIR="/opt/creative-intelligence"
DOMAIN="${DOMAIN:-creative-intelligence.duckdns.org}"
EMAIL="${EMAIL:-}"
ENV_DIR="/etc/creative-intelligence"

export SOURCE_DIR DOMAIN

echo "== 1/7 validate config =="
if [[ -z "${EMAIL}" && -z "${SKIP_HTTPS:-}" ]]; then
  echo "EMAIL is required for the Let's Encrypt certificate." >&2
  echo "Usage: sudo DOMAIN=${DOMAIN} EMAIL=admin@example.com bash deploy/oracle/setup-demo.sh" >&2
  exit 1
fi
if [[ ! -f "${SOURCE_DIR}/pyproject.toml" ]]; then
  echo "SOURCE_DIR is not the repo: ${SOURCE_DIR}" >&2
  exit 1
fi

echo "== 2/7 DuckDNS update =="
DUCKDNS_SCRIPT="${SOURCE_DIR}/deploy/oracle/duckdns-update.sh"
if [[ "${DOMAIN}" == *.sslip.io ]]; then
  echo "sslip.io fallback hostname; skipping DuckDNS registration."
elif bash "${DUCKDNS_SCRIPT}"; then
  :
else
  echo "Continuing without DuckDNS (see deploy/oracle/duckdns.env.example)." >&2
fi

echo "== 3/7 verify DNS resolution =="
if [[ -z "${SKIP_DNS_WAIT:-}" ]]; then
  for _ in $(seq 1 30); do
    if getent hosts "${DOMAIN}" >/dev/null 2>&1; then
      echo "${DOMAIN} resolves to: $(getent hosts "${DOMAIN}" | awk '{print $1}' | head -1)"
      break
    fi
    if [[ "${_}" == "30" ]]; then
      echo "DNS for ${DOMAIN} is not resolving yet; re-run once it propagates." >&2
      exit 1
    fi
    sleep 10
  done
else
  getent hosts "${DOMAIN}" || {
    echo "DNS for ${DOMAIN} does not resolve." >&2
    exit 1
  }
fi

echo "== 4/7 install or update application =="
if [[ -d "${APP_DIR}/.venv" ]]; then
  bash "${SOURCE_DIR}/deploy/oracle/update.sh"
else
  bash "${SOURCE_DIR}/deploy/oracle/install.sh"
fi

echo "== 5/7 HTTPS =="
if [[ -z "${SKIP_HTTPS:-}" ]]; then
  EMAIL="${EMAIL}" bash "${APP_DIR}/deploy/oracle/enable-https.sh"
  BASE="https://${DOMAIN}"
else
  echo "SKIP_HTTPS set: leaving plain HTTP (not for public demos)."
  BASE="http://${DOMAIN}"
fi

echo "== 6/7 restart and smoke checks =="
systemctl restart creative-intelligence
sleep 2
BASE_URL="${BASE}" bash "${APP_DIR}/deploy/oracle/verify.sh"

echo "== 7/7 callbacks to register =="
echo "Register these exact URLs (the app cannot do this for you):"
echo "  WorkOS dashboard: ${BASE}/api/auth/callback"
echo "  Google Cloud console: ${BASE}/api/auth/google/callback"
echo
echo "Public demo URL: ${BASE}"

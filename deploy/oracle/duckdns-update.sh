#!/usr/bin/env bash
# Update a DuckDNS hostname to this VM's public IPv4 address.
#
# Secrets come only from the environment or a root-only env file:
#   DUCKDNS_SUBDOMAIN  e.g. foap-creative   (required)
#   DUCKDNS_TOKEN      DuckDNS account token (required, never logged)
#   DUCKDNS_ENV_FILE   default /etc/creative-intelligence/duckdns.env
#   PUBLIC_IP          override auto-detection (optional, for testing)
#
# Prints only safe status: "<host> -> <ip>". Exits non-zero on failure.
set -Eeuo pipefail

ENV_FILE="${DUCKDNS_ENV_FILE:-/etc/creative-intelligence/duckdns.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

SUBDOMAIN="${DUCKDNS_SUBDOMAIN:-}"
TOKEN="${DUCKDNS_TOKEN:-}"
if [[ -z "${SUBDOMAIN}" || -z "${TOKEN}" ]]; then
  echo "DuckDNS is not configured: set DUCKDNS_SUBDOMAIN and DUCKDNS_TOKEN" >&2
  echo "(see deploy/oracle/duckdns.env.example)." >&2
  exit 1
fi
HOST="${SUBDOMAIN}.duckdns.org"

IP="${PUBLIC_IP:-}"
if [[ -z "${IP}" ]]; then
  IP="$(curl -fsS --max-time 15 https://api.ipify.org)" || {
    echo "Could not detect the public IPv4 address." >&2
    exit 1
  }
fi
if [[ ! "${IP}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Detected value is not an IPv4 address; refusing to update." >&2
  exit 1
fi
if [[ ! "${SUBDOMAIN}" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "Bad DUCKDNS_SUBDOMAIN value; refusing to update." >&2
  exit 1
fi
if [[ ! "${TOKEN}" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "Bad DUCKDNS_TOKEN shape; refusing to update." >&2
  exit 1
fi

# DuckDNS takes GET parameters. The token travels via a stdin config
# file (never argv, logs, or CI output); curl errors are scrubbed so a
# token can never leak through them.
if ! RESP="$(curl -fsS --max-time 30 -K - 2>/dev/null <<CURLCONF
url = "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${TOKEN}&ip=${IP}"
CURLCONF
)"; then
  echo "DuckDNS update request failed for ${HOST}." >&2
  exit 1
fi
if [[ "${RESP}" != "OK" ]]; then
  echo "DuckDNS rejected the update for ${HOST} (bad token or domain?)." >&2
  exit 1
fi

echo "DuckDNS updated:"
echo "${HOST} -> ${IP}"

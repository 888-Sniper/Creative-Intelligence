#!/usr/bin/env bash
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:4321}"
BASE_URL="${BASE_URL%/}"

curl -fsS "${BASE_URL}/health" >/dev/null
curl -fsS "${BASE_URL}/readiness" >/dev/null
curl -fsS "${BASE_URL}/" >/dev/null

code="$(curl -sS -o /tmp/ci-auth-check.$$ -w '%{http_code}' "${BASE_URL}/api/campaigns")"
trap 'rm -f /tmp/ci-auth-check.$$' EXIT
if [[ "${code}" != "401" ]]; then
  echo "Expected unauthenticated /api/campaigns to return 401, got ${code}" >&2
  cat /tmp/ci-auth-check.$$ >&2 || true
  exit 1
fi

echo "Deployment smoke check passed for ${BASE_URL}: health, readiness, frontend, and default-deny auth gate."

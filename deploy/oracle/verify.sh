#!/usr/bin/env bash
# Public-demo verification for Creative Intelligence (goal item 29).
#
#   Local (VM loopback):
#     sudo bash /opt/creative-intelligence/deploy/oracle/verify.sh
#   Public HTTPS:
#     sudo BASE_URL=https://creative-intelligence.duckdns.org \
#       bash /opt/creative-intelligence/deploy/oracle/verify.sh
#
# Optional: EXPECT_LIVE=1 fails unless the app reports provider_mode=live.
# Never prints secrets.
set -Eeuo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:4321}"
BASE_URL="${BASE_URL%/}"
SCHEME="${BASE_URL%%://*}"
HOSTPORT="${BASE_URL#*://}"
HOST="${HOSTPORT%%:*}"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0
check() { # check <name> <command...>
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok   - ${name}"; pass=$((pass + 1))
  else
    echo "FAIL - ${name}"; fail=$((fail + 1))
  fi
}
check_contains() { # check_contains <name> <file> <pattern>
  local name="$1" file="$2" pattern="$3"
  if grep -qi "$pattern" "$file"; then
    echo "ok   - ${name}"; pass=$((pass + 1))
  else
    echo "FAIL - ${name}"; fail=$((fail + 1))
  fi
}

echo "Verifying ${BASE_URL}"

if [[ "${SCHEME}" == "https" ]]; then
  echo "-- public HTTPS checks --"
  check "DNS resolves ${HOST}" getent hosts "${HOST}"
  check "HTTPS certificate valid" \
    curl -fsS --max-time 20 "${BASE_URL}/health"
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
    "http://${HOSTPORT}/health" || true)"
  if [[ "${code}" == "301" || "${code}" == "302" ||
        "${code}" == "307" || "${code}" == "308" ]]; then
    echo "ok   - HTTP redirects to HTTPS (${code})"; pass=$((pass + 1))
  else
    echo "FAIL - HTTP redirects to HTTPS (got ${code})"; fail=$((fail + 1))
  fi
fi

echo "-- application checks --"
check "/health" curl -fsS --max-time 20 "${BASE_URL}/health"
check "/readiness" curl -fsS --max-time 20 "${BASE_URL}/readiness"
check "frontend loads" curl -fsS --max-time 20 "${BASE_URL}/"

code="$(curl -sS -o "${TMP}/anon" -w '%{http_code}' --max-time 20 \
  "${BASE_URL}/api/campaigns" || true)"
if [[ "${code}" == "401" ]]; then
  echo "ok   - anonymous /api/campaigns is 401"; pass=$((pass + 1))
else
  echo "FAIL - anonymous /api/campaigns is ${code}"; fail=$((fail + 1))
fi

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 \
  "${BASE_URL}/media/1" || true)"
if [[ "${code}" == "401" || "${code}" == "404" ]]; then
  echo "ok   - anonymous /media is gated (${code})"; pass=$((pass + 1))
else
  echo "FAIL - anonymous /media is ${code}"; fail=$((fail + 1))
fi

echo "-- security header checks --"
# GET (not HEAD): the SPA fallback only answers GET.
curl -sS --max-time 20 -o /dev/null -D "${TMP}/headers" "${BASE_URL}/" || true
for h in "Content-Security-Policy" "X-Content-Type-Options" \
         "Referrer-Policy" "X-Frame-Options" "Permissions-Policy"; do
  check_contains "header ${h} present" "${TMP}/headers" "^${h}:"
done
if [[ "${SCHEME}" == "https" ]]; then
  check_contains "header Strict-Transport-Security present" \
    "${TMP}/headers" "^Strict-Transport-Security:"
fi

echo "-- session cookie checks --"
: > "${TMP}/cookies"
for provider in workos google github; do
  curl -sS --max-time 20 -o /dev/null -D - -X POST "${BASE_URL}/api/auth/oauth/start" \
    -H 'Content-Type: application/json' \
    --data "{\"provider\": \"${provider}\"}" \
    | grep -i "^set-cookie:" >> "${TMP}/cookies" || true
done
if grep -qi "ci_oauth_state" "${TMP}/cookies"; then
  check_contains "state cookie is HttpOnly" "${TMP}/cookies" "httponly"
  if [[ "${SCHEME}" == "https" ]]; then
    check_contains "state cookie is Secure" "${TMP}/cookies" ";\s*secure"
  fi
else
  echo "skip - no OAuth state cookie issued (providers may be disabled)"
fi

echo "-- provider mode checks --"
mode="$(curl -sS --max-time 20 "${BASE_URL}/api/health" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('provider_mode', ''))" \
  2>/dev/null || true)"
echo "provider_mode reported: ${mode:-unknown}"
if [[ "${EXPECT_LIVE:-}" == "1" ]]; then
  if [[ "${mode}" == "live" ]]; then
    echo "ok   - provider mode is LIVE"; pass=$((pass + 1))
  else
    echo "FAIL - provider mode is '${mode}', expected live"; fail=$((fail + 1))
  fi
fi

echo
echo "verify: ${pass} passed, ${fail} failed for ${BASE_URL}"
[[ "${fail}" == "0" ]]

#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
ENV_FILE="/etc/creative-intelligence/creative-intelligence.env"

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with sudo and supply DOMAIN/EMAIL." >&2
  exit 1
fi
if [[ -z "${DOMAIN}" || -z "${EMAIL}" ]]; then
  echo "Usage: sudo DOMAIN=foap-creative.duckdns.org EMAIL=admin@example.com bash deploy/oracle/enable-https.sh" >&2
  exit 1
fi

certbot --nginx --non-interactive --agree-tos --redirect -m "${EMAIL}" -d "${DOMAIN}"

python3 - "${ENV_FILE}" "${DOMAIN}" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
domain = sys.argv[2]
text = path.read_text() if path.exists() else ""
updates = {
    "CREATIVE_INTEL_COOKIE_SECURE": "true",
    "CREATIVE_INTEL_WORKOS_REDIRECT_URI": f"https://{domain}/api/auth/callback",
    "CREATIVE_INTEL_GOOGLE_REDIRECT_URI": f"https://{domain}/api/auth/google/callback",
}
lines = text.splitlines()
seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out).rstrip() + "\n")
PY
chmod 600 "${ENV_FILE}"
systemctl restart creative-intelligence
curl -fsS "https://${DOMAIN}/health" >/dev/null
curl -fsS "https://${DOMAIN}/readiness" >/dev/null

echo "HTTPS enabled. Register these exact callback URLs with the providers:"
echo "  WorkOS: https://${DOMAIN}/api/auth/callback"
echo "  Google: https://${DOMAIN}/api/auth/google/callback"

# Oracle Cloud VM deployment — free Foap demo (DuckDNS + HTTPS)

Target: a public **$0/month** demo at

```text
https://creative-intelligence.duckdns.org
```

stack:

```text
Oracle Cloud Always Free VM
  -> DuckDNS free hostname (creative-intelligence.duckdns.org)
  -> Let's Encrypt HTTPS (Certbot)
  -> Nginx (public 80/443, HTTP -> HTTPS redirect)
  -> FastAPI/Uvicorn on loopback 127.0.0.1:4321
  -> built React/Vite frontend served by FastAPI
```

SQLite + media persist under `/var/lib/creative-intelligence`.
Secrets live only in `/etc/creative-intelligence/*.env` (mode `0600`,
never in Git). systemd keeps services running across reboots.

Everything deploys from **`main`**. The old `deploy/oracle-always-free`
branch is retired; do not use it.

## 0. Prerequisites (your actions, not the scripts')

1. Create an Always Free Ubuntu VM in OCI (Ampere ARM is fine).
2. Security list / NSG ingress:
   - TCP 22 from your administrator IP/range only
   - TCP 80 from the internet (Let's Encrypt validation)
   - TCP 443 from the internet
   - Never expose 4321.
3. Register a free DuckDNS hostname (default `creative-intelligence`;
   alternatives if taken: `foap-creative`, `foap-ci`,
   `creative-intelligence-foap`, `foap-demo-ci`) and note its token.
   Nobody can do this for you: the hostname is claimed in your
   DuckDNS account.
4. Have ready: admin email, WorkOS client ID + API key, provider keys
   (at least one STT, one vision, one LLM adapter), and optionally
   Google OAuth credentials.

No paid domain is required. Moving to an official domain later only
needs: DNS, `DOMAIN`, the two redirect URIs, and a new certificate
(see §9).

## 1. Put the repository on the VM

```bash
git clone git@github.com:888-Sniper/Creative-Intelligence.git
cd Creative-Intelligence
git checkout main
git pull --ff-only
```

## 2. Configure secrets (on the VM only)

```bash
sudo cp deploy/oracle/demo.env.example \
  /etc/creative-intelligence/creative-intelligence.env
sudo chmod 600 /etc/creative-intelligence/creative-intelligence.env
sudo nano /etc/creative-intelligence/creative-intelligence.env
```

Fill every empty value (admin email, WorkOS, provider keys, master
key). Then the DuckDNS token:

```bash
sudo cp deploy/oracle/duckdns.env.example \
  /etc/creative-intelligence/duckdns.env
sudo chmod 600 /etc/creative-intelligence/duckdns.env
sudo nano /etc/creative-intelligence/duckdns.env
```

```text
DUCKDNS_SUBDOMAIN=creative-intelligence
DUCKDNS_TOKEN=<paste-your-duckdns-token>
```

Emergency zero-account fallback: use an sslip.io hostname instead,
e.g. `DOMAIN=123-45-67-89.sslip.io` for public IP `123.45.67.89`.
DuckDNS stays the preferred hostname.

## 3. One-command setup

```bash
sudo DOMAIN=creative-intelligence.duckdns.org EMAIL=admin@example.com \
  bash deploy/oracle/setup-demo.sh
```

This validates config, updates DuckDNS, waits for DNS, installs (or
updates) the app from `main`, configures Nginx, obtains the Let's
Encrypt certificate with HTTP->HTTPS redirect, sets the WorkOS/Google
callback URLs for this domain, restarts services, and runs `verify.sh`.
It is idempotent: re-running is safe.

Equivalent manual path:

```bash
sudo DOMAIN=creative-intelligence.duckdns.org bash deploy/oracle/install.sh
sudo DOMAIN=creative-intelligence.duckdns.org EMAIL=admin@example.com \
  bash /opt/creative-intelligence/deploy/oracle/enable-https.sh
```

The installer also enables: UFW (22/80/443, SSH allowed first so you
are never locked out), Fail2ban, automatic security updates, the
nightly backup timer, and — once the DuckDNS token is set — the
10-minute DuckDNS refresh timer.

## 4. Register callbacks (your actions)

The app cannot change provider dashboards. Register these exact URLs:

```text
WorkOS dashboard:  https://creative-intelligence.duckdns.org/api/auth/callback
Google Cloud:      https://creative-intelligence.duckdns.org/api/auth/google/callback
```

## 5. Verify

```bash
sudo BASE_URL=https://creative-intelligence.duckdns.org \
  EXPECT_LIVE=1 \
  bash /opt/creative-intelligence/deploy/oracle/verify.sh
```

This checks DNS, certificate, HTTP->HTTPS redirect, `/health`,
`/readiness`, frontend, anonymous default-deny (401), security
headers, cookie flags, media gating, and live provider mode.

Provider readiness (authenticated):

```bash
curl -sS https://creative-intelligence.duckdns.org/api/providers/status \
  -H "Cookie: ci_session=<session>"
```

must show `stt`, `vision`, and `llm` as `configured` before the Foap
demo. It never exposes key values.

## 6. Updating after a GitHub change

```bash
git pull --ff-only
sudo SOURCE_DIR="$PWD" bash deploy/oracle/update.sh
```

Backup first, install from `requirements.lock`, rebuild React, migrate,
restart, health-check. Systemd units refresh automatically.

## 7. Backups

```bash
sudo bash /opt/creative-intelligence/deploy/oracle/backup.sh
```

Nightly on-host snapshots run automatically, plus an off-host rsync
copy once `BACKUP_OFFHOST_DEST` is set (see `deploy/oracle/env.example`
and `docs/BACKUP.md`).

> **local backup ≠ disaster recovery.** Until an off-host copy is
> configured, a lost VM means lost data. The free path is OCI Object
> Storage (Always Free allowance) — see `docs/BACKUP.md`.

Restore:

```bash
sudo bash /opt/creative-intelligence/deploy/oracle/restore.sh \
  /var/backups/creative-intelligence/<timestamp>.tar.gz
```

## 8. Useful operations

```bash
sudo systemctl status creative-intelligence
sudo journalctl -u creative-intelligence -n 200 --no-pager
sudo systemctl restart creative-intelligence
sudo systemctl list-timers 'creative-intelligence-*'
sudo nginx -t
curl http://127.0.0.1:4321/health
curl http://127.0.0.1:4321/readiness
```

## 9. Moving to an official domain later

Only these change (no source-code changes):

1. DNS for the new name
2. `DOMAIN`
3. `CREATIVE_INTEL_WORKOS_REDIRECT_URI` (+ WorkOS dashboard entry)
4. `CREATIVE_INTEL_GOOGLE_REDIRECT_URI` (+ Google console entry)
5. New certificate via `enable-https.sh`

## 10. What remains outside these scripts

- creating the OCI VM and its network rules;
- claiming the DuckDNS hostname in your account;
- registering callback URLs in WorkOS/Google;
- supplying real secrets and provider keys;
- opening the final URL from another network and exercising the
  full login -> upload -> analysis -> report flow.

For a Foap pilot, use test/demo data until authentication, providers,
and privacy are live-validated on the public HTTPS deployment.

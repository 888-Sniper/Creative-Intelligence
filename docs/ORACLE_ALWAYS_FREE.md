# Oracle Cloud VM deployment (Foap demo)

This deployment target runs Creative Intelligence as a single same-origin service:

- Nginx on ports 80/443
- FastAPI/Uvicorn on loopback `127.0.0.1:4321`
- the built React/Vite frontend served by FastAPI
- SQLite + media persisted under `/var/lib/creative-intelligence`
- WorkOS/Google/provider secrets supplied only through `/etc/creative-intelligence/creative-intelligence.env`
- systemd keeps the service running across VM reboots

The scripts are designed for an Ubuntu OCI VM, including ARM64/Ampere shapes. They do not create OCI resources themselves.

## 1. Create the OCI VM

In Oracle Cloud, create an Always Free-eligible VM in your tenancy using Ubuntu. Keep the boot volume within the current Always Free allowance shown by the OCI console.

Network ingress for a public Foap test should be limited to:

- TCP 22 from your own administrator IP/range
- TCP 80 from the internet (needed for initial HTTP/Let's Encrypt validation)
- TCP 443 from the internet

Do not expose port 4321 publicly; FastAPI binds to loopback and Nginx is the public entry point.

## 2. Put the private repository on the VM

Authenticate the VM to GitHub using a deploy key, GitHub SSH key, or another approved credential. Do not paste a long-lived GitHub token into shell history.

Example after GitHub SSH access is configured:

```bash
git clone git@github.com:888-Sniper/Creative-Intelligence.git
cd Creative-Intelligence
git checkout deploy/oracle-always-free
```

## 3. Install

If you already have a DNS name pointing to the VM:

```bash
sudo DOMAIN=creative.example.com bash deploy/oracle/install.sh
```

Without a domain yet:

```bash
sudo bash deploy/oracle/install.sh
```

The installer:

1. installs Nginx, Certbot, ffmpeg, SQLite, Python 3.13 and Node 22;
2. installs pnpm and builds the React production bundle;
3. creates `/opt/creative-intelligence` for application code;
4. creates persistent `/var/lib/creative-intelligence` storage;
5. creates `/etc/creative-intelligence/creative-intelligence.env` if missing;
6. applies the Alembic migration chain to the persistent database;
7. installs and starts the systemd service;
8. configures Nginx as the reverse proxy;
9. checks `/health` and `/readiness`.

## 4. Configure secrets

Edit:

```bash
sudo nano /etc/creative-intelligence/creative-intelligence.env
```

At minimum configure:

- `CREATIVE_INTEL_ADMIN_EMAIL`
- `CREATIVE_INTEL_WORKOS_CLIENT_ID`
- `CREATIVE_INTEL_KEY_WORKOS`
- `CREATIVE_INTEL_WORKOS_REDIRECT_URI`

For private Google Drive/Sheets also configure the Google OAuth values in the template.

The file is created mode `0600`. Do not commit it.

After editing:

```bash
sudo systemctl restart creative-intelligence
```

## 5. HTTPS

A public WorkOS demo should use HTTPS and an exact registered callback URL. Once DNS points to the VM:

```bash
sudo DOMAIN=creative.example.com EMAIL=you@example.com \
  bash /opt/creative-intelligence/deploy/oracle/enable-https.sh
```

This obtains a Let's Encrypt certificate with Certbot, redirects HTTP to HTTPS, enables the application's Secure cookie setting, and updates the expected callback URLs in the server environment.

Register these exact URLs with the respective providers:

```text
https://creative.example.com/api/auth/callback
https://creative.example.com/api/auth/google/callback
```

The script cannot change provider dashboards for you.

## 6. Smoke test

Locally on the VM:

```bash
sudo bash /opt/creative-intelligence/deploy/oracle/verify.sh
```

Against the public HTTPS name:

```bash
sudo BASE_URL=https://creative.example.com \
  bash /opt/creative-intelligence/deploy/oracle/verify.sh
```

The smoke test confirms:

- liveness
- readiness/database availability
- frontend response
- unauthenticated analytics remain default-deny (`401`)

## 7. Updating after a GitHub change

Update your checked-out source branch first, then run:

```bash
git pull --ff-only
sudo SOURCE_DIR="$PWD" bash deploy/oracle/update.sh
```

The updater takes a backup first, installs backend changes, rebuilds React, applies Alembic migrations, restarts the service and runs health/readiness checks.

## 8. Backups

Manual backup:

```bash
sudo bash /opt/creative-intelligence/deploy/oracle/backup.sh
```

Archives are stored under `/var/backups/creative-intelligence` by default. They contain the SQLite database plus local creative media/avatar directories.

Copy important backups off the VM as well. A boot volume is persistent, but it is not a substitute for an independent backup.

Restore:

```bash
sudo bash /opt/creative-intelligence/deploy/oracle/restore.sh \
  /var/backups/creative-intelligence/<timestamp>.tar.gz
```

## 9. Useful operations

```bash
sudo systemctl status creative-intelligence
sudo journalctl -u creative-intelligence -n 200 --no-pager
sudo systemctl restart creative-intelligence
sudo nginx -t
curl http://127.0.0.1:4321/health
curl http://127.0.0.1:4321/readiness
```

## 10. What remains outside these scripts

The repository can prepare and run the application, but it cannot provision your Oracle account or change third-party identity-provider dashboards by itself. You still need to:

- create the OCI VM;
- attach the VM's public IP/network rules;
- point a DNS name at the VM if using public OAuth;
- register the HTTPS callback URL in WorkOS/Google;
- supply the actual production/test secrets.

For a Foap pilot, use test/demo data until the authentication, provider and privacy configuration has been live-validated on the public HTTPS deployment.

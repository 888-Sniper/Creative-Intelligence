# Render Free Demo Deployment

Public demo of Foap Creative Intelligence on a Render Free Web Service.
Additive only: the Oracle Always Free deployment (`deploy/oracle/`,
`docs/ORACLE_ALWAYS_FREE.md`) is unchanged, SQLite stays the database,
and no paid Render resources are used.

## How It Deploys

- `render.yaml` (repo root) defines ONE Web Service,
  `creative-intelligence`, `plan: free`, `runtime: docker`,
  `healthCheckPath: /health`, auto-deploy from `main`.
- `Dockerfile` (multi-stage):
  1. Node 22 + pnpm 10.14.0 installs `apps/creative-intelligence-ui`
     (`--frozen-lockfile`) and runs the production Vite build.
  2. Python 3.13-slim installs `requirements.lock` (`--require-hashes`)
     plus the project (`pip install --no-deps .`), then copies
     `Backend/`, `Web/`, `fixtures/` and the built `dist/`, which the
     FastAPI app serves at `/` when present.
- Start command (image `CMD`): `python Backend/ci_backend/main.py`.
  `main.py` binds `0.0.0.0` to `$PORT` when `PORT` is set and keeps
  `127.0.0.1:4321` otherwise, so local and Oracle behavior is unchanged.
- No `EXPOSE`: the port comes from Render's `$PORT` at runtime.

## Connect The Repo (Manual, Once)

1. Render dashboard -> New + -> Blueprint -> select
   `888-Sniper/Creative-Intelligence` (uses `render.yaml`), or create
   a Web Service manually with the Docker settings above.
2. Fill the `sync: false` secret placeholders in the dashboard
   (see Environment below). The service reports unhealthy until the
   required ones are set — that is the fail-closed behavior, not a bug.
3. After Render assigns `https://<service>.onrender.com`, register the
   callback URLs (see below), set the matching env vars, and redeploy.

## Environment Variables

Non-secret values ship in `render.yaml`. Secrets are dashboard-only.

| Variable | Value / Source |
| --- | --- |
| `CREATIVE_INTEL_ENVIRONMENT` | `demo` (fail-closed safety stays on) |
| `CREATIVE_INTEL_COOKIE_SECURE` | `true` (Render is HTTPS-only) |
| `CREATIVE_INTEL_PROVIDER_MODE` | `live` (demo must never serve mock AI) |
| `CREATIVE_INTEL_DATA_DIR` | `/app/data` (ephemeral; see below) |
| `CREATIVE_INTEL_DEMO_SEED` | `true` (seed fixtures on first boot) |
| `CREATIVE_INTEL_ADMIN_EMAIL` | dashboard secret (first admin + approvals) |
| `CREATIVE_INTEL_WORKOS_CLIENT_ID` | dashboard secret |
| `CREATIVE_INTEL_KEY_WORKOS` | dashboard secret (WorkOS API key) |
| `CREATIVE_INTEL_WORKOS_REDIRECT_URI` | dashboard secret (see Callback URLs) |
| `CREATIVE_INTEL_MASTER_KEY` | dashboard secret, Fernet key (see below) |
| `CREATIVE_INTEL_GOOGLE_CLIENT_ID` | dashboard secret (optional; Drive/Sheets) |
| `CREATIVE_INTEL_GOOGLE_CLIENT_SECRET` | dashboard secret (optional) |
| `CREATIVE_INTEL_GOOGLE_REDIRECT_URI` | dashboard secret (see Callback URLs) |
| `CREATIVE_INTEL_KEY_<SERVICE>` | dashboard secrets, only for AI providers the demo uses, e.g. `CREATIVE_INTEL_KEY_GEMINI`, `CREATIVE_INTEL_KEY_OPENAI`, `CREATIVE_INTEL_KEY_ANTHROPIC` (pattern: `CREATIVE_INTEL_KEY_` + uppercase service name, `-` -> `_`; availability is reported by `/api/providers/status`) |

Generate the master key locally (never commit it):

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

It must be a valid Fernet key — a random string from a generator
will be rejected at startup with a clear error.

## Callback URLs

After Render assigns the service URL:

- WorkOS dashboard -> redirect URI:
  `https://<service>.onrender.com/api/auth/callback`,
  then set `CREATIVE_INTEL_WORKOS_REDIRECT_URI` to the same value.
- Google Cloud console -> authorized redirect URI:
  `https://<service>.onrender.com/api/auth/google/callback`,
  then set `CREATIVE_INTEL_GOOGLE_REDIRECT_URI` to the same value.

Redeploy after saving so the new values take effect.

## Demo Database Bootstrap And Persistence

Render Free has an **ephemeral filesystem**: anything written under
`/app/data` disappears on restart/redeploy. The demo strategy is:

1. On boot, `main.py` creates `/app/data` if missing.
2. `create_app()` runs the Alembic migrations to head (same
   authoritative path as local/Oracle — no separate migration step).
3. Because `CREATIVE_INTEL_DEMO_SEED=true` and the database file did
   not exist before this boot, the bundled fixture CSVs are ingested
   once (`Meta Sample`, `TikTok Sample`, `Retention Sample`).
4. An existing database is never touched: a second boot of the same
   instance skips seeding entirely, so rows cannot duplicate and demo
   edits made during the session survive until the instance stops.
5. After a Render restart/redeploy the slate is clean again: fresh
   migrations + fresh seed. That data loss is expected and acceptable
   for a demo; it is not production storage.

Security is not weakened for the demo: `environment=demo` keeps
`require_public_safety()` active, so boot fails closed (missing
WorkOS keys, non-live provider mode, or non-secure cookies refuse to
serve). Never set `environment=local` on Render to work around this.

## Health Checks

- Liveness (Render `healthCheckPath`): `GET /health` -> `{"ok": true}`.
- Readiness: `GET /readiness` -> `{"ready": true}` once the database
  is migrated (503 with a secret-free reason otherwise).

## Render Free Spin-Down

Free instances spin down after inactivity and need a cold start
(usually under a minute: migrations + seed on a fresh filesystem)
on the next visit. That is appropriate for demo/testing, not for
production. Do not add artificial keep-alive traffic.

## Oracle Parity

Nothing under `deploy/oracle/` changed. Oracle units pass no CLI
flags and set no `PORT`, so they still bind `127.0.0.1:4321`;
`CREATIVE_INTEL_DEMO_SEED` defaults to false everywhere except the
Render service.

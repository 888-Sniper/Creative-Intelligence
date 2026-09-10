# Creative Intelligence

Local-first Performance + Creative Intelligence tool (MVP).

Upload Meta / TikTok / Excel / Sheets exports, build a canonical SQLite
dataset, compute spend-weighted benchmarks, and annotate creatives
(hook types, brand/product/logo seconds, structure, creator-vs-branded)
through a gated pipeline: ingest → transcribe → frame-sample →
vision-annotate → LLM-structure, with confidence scores and a
HUMAN-VERIFIED gate before one-pager export.

## Layout

```text
Creative Intelligence/
├── README.md                  # this file
├── docs/                      # Architecture, PROVIDERS, BACKUP, FRONTEND, Oracle guide
├── Backend/                   # FastAPI service (Nextly-aligned stack)
│   ├── ci_backend/            # app, routers, SQLAlchemy store, WorkOS client
│   ├── alembic/               # employee-access migrations
│   └── creative_intel/        # importable analytics library
├── apps/
│   └── creative-intelligence-ui/  # React + Vite frontend (same-origin)
├── deploy/
│   └── oracle/                # install/update/verify/backup scripts + systemd units
├── Source/                    # analysis library: adapters, benchmarks,
│                              # creative analysis, Q&A, reports, dashboard,
│                              # providers, deck export + self_check suite
├── Schema/
│   └── Canonical Schema V0.json  # canonical dataset definition (truth)
├── fixtures/                  # sample CSVs (Title Case file names)
├── pyproject.toml             # dependencies (uv.lock is the full graph)
├── requirements.lock          # hashed pip export of uv.lock (CI + VM install this)
├── uv.lock                    # complete resolved dependency graph with hashes
└── tests/                     # pytest suite (unittest files run under both)
```

## Quickstart

```bash
cd "/Users/simrandhillon/University Studies/Creative Intelligence"
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install --require-hashes -r requirements.lock   # exact CI-tested tree
python3 -m pytest tests/ -q                        # full suite (Nextly stack)
python3 -m unittest discover -s tests              # legacy runner (same tests)
python3 Source/self_check.py                      # analysis-library checks
python3 Backend/ci_backend/main.py --db Data/local.db   # serve on 127.0.0.1:4321
```

Frontend (same-origin React UI, served by the backend in production):

```bash
cd apps/creative-intelligence-ui
pnpm install --frozen-lockfile
pnpm typecheck && pnpm test && pnpm build
```

Free Oracle demo deploy: `docs/ORACLE_ALWAYS_FREE.md` (one command:
`sudo DOMAIN=… EMAIL=… bash deploy/oracle/setup-demo.sh`).

Open `http://127.0.0.1:4321`. Fixture load + replay:

```bash
python3 Backend/ci_backend/main.py --load-fixture --db Data/local.db
curl -X POST http://127.0.0.1:4321/api/replay/run
```

## Secrets

No secrets in the repo. Provider keys resolve environment-first
(`CREATIVE_INTEL_KEY_<PROVIDER>`, see `docs/PROVIDERS.md`), falling
back to the OS keychain on developer Macs only. The repo never
contains `.env` files, keys, or tokens; live provider calls fail
closed to mock/fixture data when no key is present. Google refresh
tokens are encrypted in the server database under
`CREATIVE_INTEL_MASTER_KEY`; the browser never sees any token.

## Google Drive (private Sheets / Drive sync)

Public links keep working with no setup. For private files:

1. Create an OAuth client (Desktop type) in Google Cloud Console with the
   redirect URI `http://127.0.0.1:4321/api/auth/google/callback`, then set
   `CREATIVE_INTEL_GOOGLE_CLIENT_ID` / `CREATIVE_INTEL_GOOGLE_REDIRECT_URI`
   and store the client secret in the OS keychain (`creative-intel-google`)
   or `CREATIVE_INTEL_GOOGLE_CLIENT_SECRET` for CI/non-macOS.
2. Set `CREATIVE_INTEL_MASTER_KEY` (generate with `python3 -c "from
   cryptography.fernet import Fernet;
   print(Fernet.generate_key().decode())"`). It encrypts stored refresh
   tokens; without it Google connect fails closed. Developer Macs
   auto-provision a keychain key when it is unset.
3. Open Settings → Google Drive → Connect Google Drive and approve
   read-only access. Access tokens (short-lived) and refresh tokens
   (encrypted) stay in the server database; the browser never sees either.
   Only read-only Drive scope is requested, and the granted scope is
   verified. Disconnect revokes at Google and wipes local state.
4. Add `"google_auth": true` to a `sheets`/`drive` sync-job params object
   (or a `/api/connect-*` payload). Without it, sync uses the public-link
   path; without a connection it fails closed with "Connect Google Drive
   in Settings". Disconnect anytime in Settings; the server wipes both tokens.

## Placement

New product folder at the workspace root. Degree folders, the Nextly AI
tree, and the Natively AI tree are untouched by design.

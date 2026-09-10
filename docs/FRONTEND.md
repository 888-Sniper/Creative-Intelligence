# Frontend and Serving (items 1–5, 51–52)

## Install

```sh
corepack enable && corepack prepare pnpm@10.14.0 --activate
pnpm --dir apps/creative-intelligence-ui install
```

## Development (frontend dev server + FastAPI backend)

```sh
# Terminal 1: backend (port 4318 to match the Vite proxy)
python3 Backend/ci_backend/main.py --db Data/creative_intel.db --port 4318
# Terminal 2: frontend dev server (http://127.0.0.1:5174, /api proxied)
pnpm --dir apps/creative-intelligence-ui dev
```

Production behaviour never depends on dev-only shortcuts: auth rides the
HttpOnly session cookie in both modes, and the backend remains
authoritative for every gate.

## Production build and serving

```sh
pnpm --dir apps/creative-intelligence-ui build
python3 Backend/ci_backend/main.py --db Data/creative_intel.db --port 4321
```

The backend serves `apps/creative-intelligence-ui/dist/` at `/` when the
build exists (with deep links, hashed-asset caching, brand files, and a
strict Content-Security-Policy), and falls back to the legacy static
`Web/Index.html` otherwise. Unknown paths still 404; `/health` and
`/readiness` are never shadowed by the SPA fallback.

## Tests

```sh
pnpm --dir apps/creative-intelligence-ui typecheck  # tsc --noEmit
pnpm --dir apps/creative-intelligence-ui test       # Vitest (jsdom)
pnpm --dir apps/creative-intelligence-ui test:e2e   # Playwright: seeds an
  # isolated DB, serves the production build + API from one backend origin
```

## Backend parity reference

Dependency comparison with Nextly AI lives in
[BACKEND_PARITY.md](BACKEND_PARITY.md). Backup/restore runbook:
[BACKUP.md](BACKUP.md).

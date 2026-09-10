# Backend Parity With Nextly AI (Item 6)

Source of truth for Nextly versions:
`Nextly AI/apps/mac-backend/pyproject.toml` and
`Nextly AI/apps/mac-ui/package.json`, inspected 2026-09-10.
Do not rely on memory; re-inspect before changing this file.

## Aligned (same family + floor)

| Nextly mac-backend | Creative Intelligence | Status |
|---|---|---|
| fastapi>=0.115 | fastapi>=0.115 | aligned |
| uvicorn[standard]>=0.32 | uvicorn[standard]>=0.32 | aligned |
| pydantic>=2.10 | pydantic>=2.10 | aligned |
| pydantic-settings>=2.6 | pydantic-settings>=2.6 | aligned |
| sqlalchemy>=2.0 | sqlalchemy>=2.0 | aligned |
| alembic>=1.14 | alembic>=1.14 | aligned |
| httpx>=0.28 | httpx>=0.28 | aligned |
| python-multipart>=0.0.12 | python-multipart>=0.0.12 | aligned |
| keyring>=25.0 | keyring>=25.0 | aligned (`ci_backend/credentials.py`) |
| pytest>=8.3 | pytest>=8.3 | aligned |
| pytest-asyncio>=0.24 | pytest-asyncio>=0.24 | aligned (`asyncio_mode = "auto"`) |
| ruff>=0.8 (dev) | ruff>=0.8 (dev) | aligned; identical lint config (line-length 110, py313, E/F/I) |

## Deliberate differences (documented, not gaps)

- **jsonschema>=4.23 (Nextly) — not adopted.** The API boundary is
  validated with Pydantic request models (item 37); ingest rows go
  through domain validation (`normalise.validate_row`) with quarantine,
  not JSON-Schema documents. No JSON-Schema consumer exists, so adding
  the dependency would be purely decorative.
- **websockets>=14 (Nextly `flux_stream`) — not adopted.** Creative
  Intelligence is request/response local-first; there is no streaming
  endpoint to serve. Revisit only if a streaming API is introduced.
- **Cryptography family — stdlib suffices.** Neither Nextly
  mac-backend nor Creative Intelligence declares `cryptography`.
  Session-token hashing and PKCE S256 use stdlib `hashlib`
  (`ci_backend/employees.py`, `ci_backend/workos.py`); there is no
  JWT/asymmetric need. No weaker-custom-impl situation: SHA-256 token
  hashes + `secrets`-grade tokens are the same construction class.
- **nextly-protocol / nextly-prompting / nextly-retrieval, pypdf,
  pymupdf, python-docx — Nextly-specific.** Report output here uses
  the tested hand-rolled OOXML builder plus openpyxl/python-pptx for
  ingest; verified by structural tests (app-open validation stays a
  live-validation item).
- **Ruff scope.** Nextly lints its backend package; here CI runs
  `ruff check Backend tests Source` (same rule set).

## Frontend versions recorded for the React migration (items 1-2)

From Nextly `apps/mac-ui/package.json` (do not guess):

- react / react-dom ^19.1.1, react-router-dom ^7.8.0
- typescript ^5.9.2, vite ^7.1.3, vitest ^3.2.4
- @playwright/test ^1.55.0, @vitejs/plugin-react ^4.7.0
- @fontsource-variable/geist ^5.3.0, jsdom ^26.1.0
- packageManager pnpm@10.14.0

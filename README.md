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
├── docs/
│   ├── Architecture.md
│   └── PROVIDERS.md           # provider mirror (cf. Nextly AI docs/PROVIDERS.md)
├── Backend/                   # stdlib-only Python (sqlite3 + http.server)
│   └── creative_intel/        # importable package
├── Source/                    # analysis library: adapters, benchmarks,
│                              # creative analysis, Q&A, reports, dashboard,
│                              # providers, deck export + self_check suite
├── Schema/
│   └── Canonical Schema V0.json  # canonical dataset definition (truth)
├── Web/
│   └── Index.html             # Main / Campaign / Creative / Compare / Benchmark views
├── fixtures/                  # sample CSVs (Title Case file names)
└── tests/                     # unittest suite (stdlib only)
```

## Quickstart (no dependencies, no secrets)

```bash
cd "/Users/simrandhillon/University Studies/Creative Intelligence"
python3 -m unittest discover -s tests -v          # run tests
python3 Source/self_check.py                      # analysis-library checks
python3 Backend/server.py --db Data/local.db      # serve UI + API on 127.0.0.1:4321
```

Open `http://127.0.0.1:4321`. Fixture load + replay:

```bash
python3 Backend/server.py --load-fixture --db Data/local.db
curl -X POST http://127.0.0.1:4321/api/replay/run
```

## Secrets

No secrets in the repo. Provider keys live in macOS Keychain only
(see `docs/PROVIDERS.md`). The repo never contains `.env` files, keys,
or tokens; live provider calls fail closed to mock/fixture data when no
key is present.

## Placement

New product folder at the workspace root. Degree folders, the Nextly AI
tree, and the Natively AI tree are untouched by design.

# Creative Intelligence — audit of the second-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `5336e41171cf27ab6c1fbfbf23664adfb54eae33`
  (code `8d60451` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `6e7c003f9134a5571b21c44a49373fbe26c3d07b`
  (`Fix the second-round audit defects (managed video threads, GA4 ownership, races)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `6e7c003` on this push touch only this `Audit.md`;
  review the code at `6e7c003` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 5336e41171cf27ab6c1fbfbf23664adfb54eae33 6e7c003f9134a5571b21c44a49373fbe26c3d07b
git diff 5336e41171cf27ab6c1fbfbf23664adfb54eae33 6e7c003f9134a5571b21c44a49373fbe26c3d07b
git rev-parse 6e7c003f9134a5571b21c44a49373fbe26c3d07b    # must resolve
git diff --stat 6e7c003f9134a5571b21c44a49373fbe26c3d07b HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 15 files, 318 insertions, 129
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 6e7c003:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. For full history read the earlier audits in git
history: `git show fbb9a65:Audit.md` (base `5dcb3a0`, code
`d6a8ae7`) and `git show 5336e41:Audit.md` (parent `fbb9a65`, code
`8d60451`). This push answers the second review of `8d60451`
(9 fixed / 3 partly fixed, 8 remaining defects, plus its
"Requirements missing" list); re-verify those first, then hunt wider.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `6e7c003`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `6e7c003`,
  and the evidence (quoted code or a minimal reproduction by
  reasoning over the code). No evidence, no defect — list it under
  "Unverified" instead.
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end. They are blockers/unverified, recorded below.
- Do NOT report an item as open when the cited lines do what the
  matching section says. Conversely, do NOT mark an item fixed from
  a summary, a comment, or a test name — open the implementation.
  For each of the second review's 8 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code: a test that encodes
  the same wrong assumption as the fix proves nothing.
- Secrets: never print a credential value. If you find one in the
  diff, report file and line only, redacted.

## Required output format

1. `Second-review 8 defects` — one verdict line each (fixed /
   partly fixed / still open) with file:line evidence at `6e7c003`.
2. `Defects still true` — numbered, severity-ordered (above format).
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per numbered section
   below, naming what you actually opened. Silence is not a pass.
5. `Unverified` — anything you could not confirm by reading, and
   exactly what run/access would settle it.
6. End with one verdict sentence: ship / ship after fixes / do not
   ship, naming the blocking items by number.

## What the implementer claims — falsify each one

### 1. Managed video credentials work in worker threads (was P1)

Claim. `_managed_credentials(conn)` (`video_analysis.py`) resolves
`{provider: (secret, base_url)}` once on the worker thread;
`run()` builds `LiveVision(roster, secret_for=lambda p: creds.get(p))`
— plain dict reads, no DB access in the frame thread pool.
`LiveVision._annotate_batch` unpacks `(secret, base_url)` into
`make_chat`. Try: any remaining DB/conn use inside `race()` workers;
secret/base for non-Gemini managed providers; `_resolve` raising the
not-configured sentinel (must degrade to `{}`, not crash the job);
thread-safety of the shared `creds` dict and `last_winner`.

### 2. Managed Gemini transcription

Claim. `GeminiStt(models, secret, base_url)` (`providers.py`) passes
both into `GeminiChat`; `run()` enables it when legacy Gemini is
configured OR `"gemini" in creds`. Try: managed-only install with
speech, silent clip vs transcription failure honesty, base-URL
providers whose Gemini-compatible endpoint rejects audio parts.

### 3. Analyst conversation races and scope fidelity

Claims. First-question sends are guarded too: append happens only
when `data.conversation_id === activeIdRef.current`, or when both
sent-in and visible ids are null (`AnalystPage.tsx`, `send()`).
Restored scope keeps the FULL multi-value map as `restoredScope`
(submitted verbatim) while controls show first values; any drift
from the restored first values clears the override. Try: React
batching assumptions in the drift effect (clear-then-set in one
tick); scope keys outside `FilterValues`; restored scope surviving
into a NEW conversation; objective/language vs scope disagreement.

### 4. Settings/AppShell preference freshness

Claims. Both server-merge sites capture `revRef` at fetch start and
discard the response if any commit landed meanwhile
(`SettingsPage.tsx`). `SERVER_PREF_MAP`/`toServerPrefs`/
`mergeServerPrefs` moved to `state/prefs.ts`; `AppShell.tsx`
fetches `/api/preferences` at account init, merges server-first,
persists locally, and applies theme/accent/density — a fresh
browser no longer needs a Settings visit. Try: AppShell fetch
racing a Settings edit (no rev guard there — can it clobber?);
account switch mid-fetch (`live` flag scope); theme select in
Settings vs shell-applied mode disagreeing.

### 5. GA4 ownership, selector truth, cap

Claims. `ga4_rows` UNIQUE now includes `imported_by` (DDL +
`_migrate_ga4_owner_unique` rebuild in `schema.py`); the upsert no
longer overwrites `imported_by`. The 250000-row cap is checked
before every success exit in `fetch_rows`. `Ga4Tools` reloads and
clears rows on property change and shows a property column. Try:
migration on a database with duplicate legacy rows, foreign keys /
indexes lost in the rebuild, concurrent imports by two employees,
cap boundary at exactly 250000/250001, selector showing rows while
a reload is in flight.

### 6. No raw fetch left for exports/uploads

Claims. Campaign/Creative/Benchmark exports use `apiBlob`;
`uploadMedia` uses `apiForm`; `importDataset` uses `api()` and
recovers sheet lists from `ApiError.body` (new field, populated in
`parse()`; bare 401 also re-gates). Grep should find no
`fetch("/api…` outside `api/client.ts`. Try: `SheetConflictError`
flow end to end (envelope shapes), error-message regressions from
`errorMessage` removal at those sites, downloads that relied on
saving non-2xx bodies, any `fetch(` with template-built `/api`
URLs the grep missed.

### 7. Tests actually cover the races

Claims. New in `tests/test_gap_completion.py` (18 total):
two-employee same-property GA4 imports keep both owners' rows;
two-thread same-dedup-key enqueue sends exactly once (file DB +
barrier); `GeminiStt` forwards managed secret/base into
`GeminiChat`. Judge whether the thread test would fail against the
pre-fix claim-after-send code, and name still-missing coverage
(e.g. eager credential resolution under a thread-bound connection,
250001-row cap, first-question race UI test).

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 18 passed.
- `pytest tests/test_video_analysis.py tests/test_analyst_api.py
  tests/test_provider_status.py`: 84 passed.
- `pnpm test`: 328 passed. `pnpm exec tsc --noEmit`: clean (one
  cast fix in the drift effect). `pnpm build`: passed. Ruff on
  changed Python: clean.
- The full 899-test backend run from the first push was NOT
  repeated for either fix push — flag any area whose risk makes
  that omission matter.
- Gemini key re-probed before this push: still absent (env, login
  shell, launchctl, Keychain). Live workflow remains unverified.

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED.** `CREATIVE_INTEL_KEY_GEMINI` empty
  everywhere checked. No live model call, job id, browser
  click-through, or screenshot exists for any push. Unblock: set
  the key (env or Keychain `creative-intel-gemini`),
  `CREATIVE_INTEL_PROVIDER_MODE=live`, activate a Gemini model in
  AI Providers, run `04-quentin-retargeting-si.mp4` through the
  wizard, reload, download, compare findings.
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_*`.
- **Meta/TikTok/GA4 live OAuth/imports: BLOCKED** on console
  credentials in `docs/RENDER.md`.
- **Production:** Render auto-deploys `main`; no deployment of any
  push was verified.

## Known still-open items (already admitted — only re-report if worse)

- Scheduled GA4 sync not implemented (manual import only);
  `sync.py` sources still exclude GA4.
- Privacy toggles (data usage / share analytics / retention) are
  persisted preferences; no telemetry or server retention engine
  exists behind them. Check copy does not claim enforcement.
- Admin "teams" are browser-local; no per-employee team backend.
- Deterministic Analyst tables render en/pl only; Spanish is the
  provider narrative.
- Compare page hardcoded English copy (pre-existing).
- Five pre-existing backend failures on the original base,
  unchanged here: `test_no_licensing_concepts` (.venv walker),
  three `test_ci_migrations.py` tests,
  `test_deploy_migration_command_from_repo_root` (`0012` vs `0013`).

# Creative Intelligence — audit of the ninth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `0bf4bb78d3c8068cfe0da23f45931d5f0411ca6e`
  (code `63020ee` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `28f9a63761e9698a0fb4fee53bce2afbffd3bc58`
  (`Fix the ninth-round audit defects (pending preference changes, saved views)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `28f9a63` on this push touch only this `Audit.md`;
  review the code at `28f9a63` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 0bf4bb78d3c8068cfe0da23f45931d5f0411ca6e 28f9a63761e9698a0fb4fee53bce2afbffd3bc58
git diff 0bf4bb78d3c8068cfe0da23f45931d5f0411ca6e 28f9a63761e9698a0fb4fee53bce2afbffd3bc58
git rev-parse 28f9a63761e9698a0fb4fee53bce2afbffd3bc58    # must resolve
git diff --stat 28f9a63761e9698a0fb4fee53bce2afbffd3bc58 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 8 files, 329 insertions, 87
deletions, frontend only (no backend changes this round). If
yours disagrees, stop and say so. A behind local checkout, or no
local `main` branch, is not a reason to stop. Read files at the
reviewed commit (`git show 28f9a63:PATH` if needed); if a later
edit moves a line, follow the symbol, not the stale number.
Earlier audits live in git history (most recently
`git show 0bf4bb7:Audit.md`, parent `018a937`, code `63020ee`).
This push answers the ninth review of `63020ee` (defects 1–4);
re-verify those first, then hunt wider. Earlier rounds' fixed
items should be regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `28f9a63`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `28f9a63`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each of the ninth review's 4 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Ninth-review 4 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

The save model changed: payloads are no longer derived from a
local-vs-snapshot diff at all. Each commit queues ONLY the keys
it changed (`serverPrefsChanges` + pending map, `prefs.ts`);
`flushServerPrefs` sends the accumulated pending batch and
confirms exactly the sent key/value pairs on acceptance.

### 1. Post-reconcile saves cannot overwrite another tab's change

Claim. The batch can only contain keys some commit in this tab
actually edited, so a diverged form value is never emitted; and
after each accepted flush `reconcileLocal` (`SettingsPage.tsx`)
adopts confirmed server values for all non-pending keys into
the form + local copy. Try: an edit queued behind the conflict
(same key AND different key); reconcile adopting a server value
for a key the user changed via the header theme toggle between
PUT and response; reconcile while the workspace-name debounce
is mid-typing (workspace excluded — what about the debounce
then committing a name typed against the pre-reconcile form?);
`confirmPrefsChanges` value-equality for boolean toggles
flipped twice in flight.

### 2. Editing before hydration cannot overwrite server preferences

Claim. Two layers: payloads are changed-keys-only regardless of
snapshot, and `flushServerPrefs` GETs first when this tab has
no snapshot to establish base/snapshot before any PUT. Try:
GET fails AND localStorage holds a stale `serverPrefsRevision`
from an older session (base fallback path into 409/retry);
Settings' own GET merge racing the flush GET (snapshot noted
twice, rev guards); controls editable during employee loading
with id `""` — pending queued under `""`, then identity arrives:
whose pending flushes, under what stamp?

### 3. Reset Defaults resets every server key

Claim. Reset commits with `replaceAll`, replacing the pending
batch with the full defaults document; the conflict retry
re-sends that full batch on the fresh base. Try: reset while a
normal edit is still in flight (replace supersedes its pending
keys — its flush may already hold the old batch); reset in a
tab whose snapshot is null (hydration GET inside flush vs the
full batch ordering); reset's toast appearing before server
acceptance (`notifyOk` fires synchronously in `resetDefaults` —
decide whether that toast wording claims more than the footer
status does).

### 4. Saved-view apply records the remembered campaign status

Claim. `applySavedView` now marks touched with the view's
status (or `""`) for the caller's account; both callers
(Insights, Benchmarks) pass `useOptionalAuth` employee id.
Try: other programmatic status writers still unmarked (grep
every `setFilter("status"` and saved-view-like restore: report
templates applying scope? deep links?); the comparison-deep-
link branch (status axis still set + marked — intended?);
callers rendering before identity loads (id `""` mark vs the
id Campaigns reads); views whose status value is `"all"`.

### 5. Tests

Claims. Conflict test extended: after retry, the density
control shows the other tab's value and a subsequent accent
edit sends exactly `{accent}`. New: pre-hydration edit (GET
500s) sends exactly `{theme}`; cross-tab Reset re-sends the
full defaults incl. density after 409; a revert made while
the first PUT is artificially HELD still lands as a second
PUT (the queued-behind case the last review asked for);
pending-map unit tests; saved-view status marking test. The
storage-retry test now polls for the async saved status
(reviewer's flake hypothesis) — check whether the asserted
sequence can still pass spuriously. Still missing (admitted):
page-level Analyst→Campaigns and saved-view→Campaigns
navigation tests (mechanisms unit-covered); three-tab
double-409 test.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 343 passed (5 new/changed net). `pnpm exec tsc
  --noEmit`: clean. `pnpm build`: passed.
- Backend untouched this round; sanity re-run
  `pytest tests/test_gap_completion.py`: 23 passed. The full
  backend run (911 passed / 5 named pre-existing failures) is
  from the eighth round on identical backend code.
- Gemini key re-probed (env + Keychain): still absent; user
  previously chose "skip live run". Live workflow unverified.

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED** on `CREATIVE_INTEL_KEY_GEMINI`
  (env or Keychain `creative-intel-gemini`) + live mode + an
  activated Gemini model. No live call, job id, browser session,
  FPS figure, or screenshot exists for any push.
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_*`.
- **Meta/TikTok/GA4 live OAuth/imports: BLOCKED** on console
  credentials in `docs/RENDER.md`.
- **Production:** Render auto-deploys `main`; unverified.

## Known still-open items (already admitted — only re-report if worse)

- Scheduled GA4 sync not implemented (manual import only).
- Privacy toggles are persisted preferences; no telemetry or
  server retention engine exists behind them.
- Admin "teams" are browser-local; no per-employee team backend.
- Deterministic Analyst tables render en/pl only; Spanish is the
  provider narrative. Compare page English copy (pre-existing).
- Five pre-existing backend failures on the original base:
  `test_no_licensing_concepts` (.venv walker), three
  `test_ci_migrations.py` tests,
  `test_deploy_migration_command_from_repo_root` (`0012` vs `0013`).

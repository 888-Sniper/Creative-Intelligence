# Creative Intelligence — audit of the sixteenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `0cb60828177f5908d2d6d5139cde6b33d1cba441`
  (code `573b2ac` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `35179f54429924968d97449efd8f5c21f7fcc474`
  (`Fix the sixteenth-round audit defect (recovery across navigation)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `35179f5` on this push touch only this `Audit.md`;
  review the code at `35179f5` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 0cb60828177f5908d2d6d5139cde6b33d1cba441 35179f54429924968d97449efd8f5c21f7fcc474
git diff 0cb60828177f5908d2d6d5139cde6b33d1cba441 35179f54429924968d97449efd8f5c21f7fcc474
git rev-parse 35179f54429924968d97449efd8f5c21f7fcc474    # must resolve
git diff --stat 35179f54429924968d97449efd8f5c21f7fcc474 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 4 files, 138 insertions, 28
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 35179f5:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show 0cb6082:Audit.md`,
parent `bf0556f`, code `573b2ac`). This push answers the
sixteenth review of `573b2ac` (one P2 defect); re-verify it
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `35179f5`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `35179f5`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For the P2 defect, state explicitly: fixed / partly fixed /
  still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Sixteenth-review defect` — verdict with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Failed-save recovery survives navigation

Claim. Commit generations and save outcomes moved to
module-level per-account state in `prefs.ts` (beside the
pending map), and Settings mount now retries any pending
edits once per account, settling the status from the real
result (`SettingsPage.tsx` recovery effect). Try: the
reviewer's exact sequence; reopening while the original
flush is STILL in flight (chain serialization + generation
guards across mounts — the unmounted page's settle handlers
vs the new page's recovery settle); account switch A→B→A
within one tab (per-account outcome/pending isolation, the
recovery guard keyed by account); recovery flush racing the
mount GET merges (snapshot noting order, reconcile sources);
recovery when pending exists but the last outcome was a
success (can that state exist?); a full page RELOAD after
failure (module state dies — what is honestly recovered from
local storage + server GET, and what is lost?).

### 2. Tests

Claims. New end-to-end test: density PUT gated to fail →
Retry → unmount → remount (recovery retries, fails again,
Retry + error restored) → clear name (validation keeps
Retry) → gate opens → Retry flushes `{density: "Compact"}`
and settles saved. Unit tests for per-account
generation-ordered outcomes. Still missing (admitted):
legacy-GET remount at page level; fresh-module new-tab
tests; Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 358 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- Backend untouched this round (round-eight full run on
  near-identical backend: 911 passed / 5 named failures).
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

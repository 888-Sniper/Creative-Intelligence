# Creative Intelligence — audit of the twelfth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `dbebd4f3db2e5b538cf530fc9af920050e4ce27f`
  (code `6a9829c` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `7f8f708d00431c95908750e28855524fe709fdac`
  (`Fix the twelfth-round audit defects (reset timer, legacy revisions)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `7f8f708` on this push touch only this `Audit.md`;
  review the code at `7f8f708` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat dbebd4f3db2e5b538cf530fc9af920050e4ce27f 7f8f708d00431c95908750e28855524fe709fdac
git diff dbebd4f3db2e5b538cf530fc9af920050e4ce27f 7f8f708d00431c95908750e28855524fe709fdac
git rev-parse 7f8f708d00431c95908750e28855524fe709fdac    # must resolve
git diff --stat 7f8f708d00431c95908750e28855524fe709fdac HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 6 files, 95 insertions, 5
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 7f8f708:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show dbebd4f:Audit.md`, parent `b974235`, code `6a9829c`).
This push answers the twelfth review of `6a9829c` (defects 1–3);
re-verify those first, then hunt wider. Earlier rounds' fixed
items should be regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `7f8f708`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `7f8f708`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each of the twelfth review's 3 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Twelfth-review 3 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Reset Defaults cannot be undone by a pending name timer

Claim. `resetDefaults` clears the debounce timer and rewrites
the draft before committing (`SettingsPage.tsx`). Try: timer
already fired and its name commit is queued/in-flight when
Reset is clicked (replace-pending vs an already-taken batch —
which workspace wins, in what order do the flushes land?);
Reset, then immediately typing a new name (fresh timer must
work); Reset while the draft equals a non-default saved name
(the round-11 draft-sync path).

### 2. Legacy unversioned preferences are explicitly version 0

Claim. Backend `get_prefs` normalizes every read to carry an
integer `_rev` (legacy/missing/corrupt ⇒ 0)
(`Backend/creative_intel/notifications.py`), and the client's
staleness check also treats an unversioned non-empty payload
as 0 (`prefs.ts`). Try: consumers of `get_prefs` beyond the
API (`data_export.py`, notification opt-in reads — does an
injected `_rev` leak anywhere user-visible or change export
contents?); a stored `_rev` that is a bool/float/string
(`isinstance(True, int)` is True in Python — trace it);
client/server disagreement during a rolling deploy (old
client vs new backend and vice versa); the conflict (409)
body for a legacy row.

### 3. "All Changes Saved" waits for an outstanding name draft

Claim. A commit's completion sets `saving` (not `saved`) while
the trimmed name draft differs from that commit's workspace
value. Try: draft typed AFTER the unrelated commit but before
its flush settles (the input handler's revision bump vs the
completion guard — which wins?); draft retyped to exactly the
saved name (timer still pending: status path); draft cleared
to empty (error path interaction); name commit's own
completion when the user typed FURTHER characters after the
timer fired but before its flush settled.

### 4. Tests

Claims. Backend: legacy row → `_rev: 0` on read, first save →
1, missing row → `{"_rev": 0}`. Frontend: unversioned payload
is stale against a confirmed snapshot and cannot replace it;
Reset-with-pending-typed-name (fake timers) sends no typed
name and restores the default in the input; the round-11
mixed-edit test now asserts "Saving…" mid-window. Still
missing (admitted): a Settings test driving an actual legacy
(no-`_rev`) GET through the remount sequence (unit-covered at
the prefs layer); true fresh-module new-tab tests; page-level
Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 351 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- `pytest tests/test_gap_completion.py`: 24 passed; prefs/
  export/notification-filtered backend run: 27 passed. Full
  backend suite not repeated this round (only `get_prefs`
  changed; round-eight full run on near-identical backend:
  911 passed / 5 named failures).
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

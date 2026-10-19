# Creative Intelligence — audit of the tenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `3a371b0cf10623439f564cb8da326ef0b3bc24ac`
  (code `28f9a63` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `7c7412bf810ca9f3b2f11eda50458a069865d396`
  (`Fix the tenth-round audit defects (edit generations, retry queueing)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `7c7412b` on this push touch only this `Audit.md`;
  review the code at `7c7412b` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 3a371b0cf10623439f564cb8da326ef0b3bc24ac 7c7412bf810ca9f3b2f11eda50458a069865d396
git diff 3a371b0cf10623439f564cb8da326ef0b3bc24ac 7c7412bf810ca9f3b2f11eda50458a069865d396
git rev-parse 7c7412bf810ca9f3b2f11eda50458a069865d396    # must resolve
git diff --stat 7c7412bf810ca9f3b2f11eda50458a069865d396 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 4 files, 167 insertions, 31
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 7c7412b:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show 3a371b0:Audit.md`,
parent `0bf4bb7`, code `28f9a63`). This push answers the tenth
review of `28f9a63` (defects 1–3); re-verify those first, then
hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `7c7412b`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `7c7412b`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each of the tenth review's 3 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Tenth-review 3 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Retry after a storage failure actually sends the edit

Claim. `commit` queues the commit's changed keys into the
pending map BEFORE attempting `savePrefs` (`SettingsPage.tsx`),
so a storage failure leaves the intent queued; Retry's
re-commit (empty diff against the already-updated form) still
flushes it. Try: storage fails, user instead REVERTS the
control without Retry (pending overwritten by the revert queue
— right outcome?); storage fails during `reconcileLocal`'s own
`savePrefs` (return value ignored there — what diverges?);
storage fails on the very first commit in a tab whose flush
chain already has an item from a prior mount (module-scoped
chain + pending across mounts/account switches — pending is
keyed per employee, but trace a stamp/flush interleave).

### 2. Confirmation is by edit generation, not value

Claim. Pending entries carry a per-edit sequence (`prefs.ts`);
`takePendingBatch` captures values+seqs together and
`confirmPrefsChanges` drops only exact generations the
accepted batch carried. Try the reviewer's sequence end-to-
end in source, then variants: Reset (`replacePendingPrefs`,
one seq for all keys) queued while a normal batch is in
flight; two keys edited in SEPARATE commits riding one batch
(different seqs, one key re-edited in flight); sequence
counter shared across accounts (global `_pendingSeq` — any
cross-account confirm risk, given maps are per-employee?);
batch taken, then the SAME commit's flush retries after 409 —
confirm uses the retry's batch seqs (same batch object?).

### 3. Combined edits cannot skip reconciliation

Claim. An empty flush now resolves with the latest confirmed
snapshot (`flushServerPrefs`) instead of `null`, so the newest
commit's completion handler always reconciles the form. Try:
empty flush resolving with a snapshot taken BEFORE another
tab's newer save (reconcile adopts stale-but-confirmed values
— can that move the form BACKWARD vs a fresher GET merge that
landed in between?); snapshot `{}` (server had no prefs)
through `mergeServerPrefs`; reconcile adopting a value for a
key whose newer edit is queued in a LATER chain item whose
flush has not run yet (pending filter uses current pending —
trace the interleave); three rapid commits where the middle
one's handler is the last to run.

### 4. Tests

Claims. Storage-retry test now asserts a real PUT carrying
`{density: "Compact"}` after Retry. New Settings tests: Dark
held in flight → Light → Dark re-selection produces TWO
`{theme:"dark"}` PUTs; combined theme+accent edits during
held GETs reconcile density to the server's Compact. prefs
unit tests cover generation confirmation incl. the equal-
value case. Check the held-GET mock faithfully models both
GET waiters (Settings merge GET + flush hydration GET).
Still missing (admitted): page-level Analyst→Campaigns and
saved-view→Campaigns navigation tests; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 346 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- Backend untouched this round (full run from round eight on
  identical backend code: 911 passed / 5 named failures).
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

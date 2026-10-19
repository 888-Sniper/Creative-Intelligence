# Creative Intelligence — audit of the eighteenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `a36bc3d82fb809c5aca26c7833461164ec08dc07`
  (code `e25d38a` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `43bc721c93157e56c9f401ad5cf77cb3e6c4c305`
  (`Fix the eighteenth-round audit regressions (hydration replay, StrictMode)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `43bc721` on this push touch only this `Audit.md`;
  review the code at `43bc721` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat a36bc3d82fb809c5aca26c7833461164ec08dc07 43bc721c93157e56c9f401ad5cf77cb3e6c4c305
git diff a36bc3d82fb809c5aca26c7833461164ec08dc07 43bc721c93157e56c9f401ad5cf77cb3e6c4c305
git rev-parse 43bc721c93157e56c9f401ad5cf77cb3e6c4c305    # must resolve
git diff --stat 43bc721c93157e56c9f401ad5cf77cb3e6c4c305 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 2 files, 79 insertions, 4
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 43bc721:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show a36bc3d:Audit.md`,
parent `9c7f051`, code `e25d38a`). This push answers the
eighteenth review of `e25d38a` (two lifecycle regressions);
re-verify those first, then hunt wider. Earlier rounds' fixed
items should be regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `43bc721`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `43bc721`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each regression, state explicitly: fixed / partly fixed /
  still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Eighteenth-review regressions` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Employee loading cannot cancel preference hydration

Claim. `serverMergedFor` is now set only when a GET response is
ACCEPTED (after live/account/revision/staleness guards), so an
effect replay that discards the first response causes the
replacement effect to refetch (`SettingsPage.tsx` merge
effect). Try: accepted-but-empty responses (marked — intended?);
fetch failure then identity flip (retry on replay?); double
GETs racing after replay when the first was NOT discarded by
cleanup yet (two in flight, both "live" at different times);
the identity-adopt branch (`id !== prefOwner`) never setting
the marker (later first-branch run refetches — harmless or a
loop?); StrictMode double-setup issuing two GETs whose both
responses arrive (first discarded by `live`, second merges —
trace the snapshot noting order).

### 2. StrictMode replay cannot permanently disable settle handlers

Claim. The mount effect restores `mountedRef` on setup.
Try: every other cleanup-only flag in the page under replay
(`recoveryFor` already consumed by the first setup — second
setup skips recovery while the first setup's flush settles
against `stillCurrent`; `serverMergedFor` interplay above;
name timer refs); AppShell and other pages for the same
cleanup-without-restore pattern (`grep` for refs set false in
cleanups); production build (no double-invoke — confirm no
behavior depends on it).

### 3. Tests

Claims. Two new tests were verified to FAIL against the
pre-fix source (implementer stashed `SettingsPage.tsx` only:
both failed; restored: pass): a production-shaped gated mount
(identity present at first render) proving hydration survives
the employee-load effect replay, and a StrictMode render
proving merge + saved feedback work. Judge whether the gated
mount really reproduces the production ordering (AuthProvider
child effects vs the page's own `/api/auth/me` load) and
whether vitest's React build actually double-invokes effects
(the pre-fix failure suggests it does — verify from source
config if you can). Flake disclosure: the first full-suite
run this round failed with ONE unidentified failure (output
truncated before capture); the immediate rerun passed 361/361
and file/isolated runs pass consistently. The implementer did
not identify which test flaked this time.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 361 passed (final run; see flake disclosure).
  `pnpm exec tsc --noEmit`: clean. `pnpm build`: passed.
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

- No durable recovery across a full page reload: pending edits
  and outcomes are memory-only.
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

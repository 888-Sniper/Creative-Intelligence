# Creative Intelligence — audit of the thirteenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `c25fa1fbc1b9514eaac9af3c8d8cf974a001e4ed`
  (code `7f8f708` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `6f779bf3d52175af0ab7dce7fda287cc03b5378b`
  (`Fix the thirteenth-round audit defects (validation vs save failure)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `6f779bf` on this push touch only this `Audit.md`;
  review the code at `6f779bf` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat c25fa1fbc1b9514eaac9af3c8d8cf974a001e4ed 6f779bf3d52175af0ab7dce7fda287cc03b5378b
git diff c25fa1fbc1b9514eaac9af3c8d8cf974a001e4ed 6f779bf3d52175af0ab7dce7fda287cc03b5378b
git rev-parse 6f779bf3d52175af0ab7dce7fda287cc03b5378b    # must resolve
git diff --stat 6f779bf3d52175af0ab7dce7fda287cc03b5378b HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 4 files, 97 insertions, 10
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 6f779bf:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show c25fa1f:Audit.md`, parent `dbebd4f`, code `7f8f708`).
This push answers the thirteenth review of `7f8f708` (one P2
defect plus the boolean-`_rev` gap it flagged); re-verify those
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `6f779bf`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `6f779bf`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For the P2 defect and the boolean-`_rev` gap, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Thirteenth-review findings` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Name validation can no longer hide a save failure (or stick on Saving)

Claim. A `saveFailedRef` records the last settled outcome;
blank-name validation restores `"error"` when a failure is
recorded, leaves state alone while changes are pending, and
only idles when nothing is outstanding. Symmetrically, a
successful settle treats a BLANK draft as not outstanding, so
it cannot stick on "Saving…" (`SettingsPage.tsx`). Try every
ordering: failure → validation (the reported case); validation
→ success; validation → failure; keystroke (which sets
`saving` unconditionally in `onWorkspaceInput`) while an error
+ Retry is showing, followed by (a) a valid name commit whose
flush also carries the failed keys, (b) deleting back to
blank; local-storage failure (not PUT) as the recorded
failure; a second mount inheriting `saveFailedRef` (it is a
per-mount ref — is anything owed across mounts given pending
keys are module-level?).

### 2. Boolean `_rev` values are malformed, not revision 1

Claim. Backend `_is_int` excludes bool in `get_prefs`
normalization, current-revision extraction, and
`base_revision` acceptance (`Backend/creative_intel/
notifications.py`). Try: `_rev` as float (`3.0`), string
(`"3"`), negative, and huge int through `get_prefs`,
`save_prefs`, the 409 body, and the client's ordering; a
client sending `base_revision: true` end-to-end (router →
409 vs 500?).

### 3. Tests

Claims. New Settings tests drive both orderings with fake
timers (failed PUT inside the debounce window keeps Retry +
error status after validation; held successful PUT released
after validation settles to saved with the name error still
visible). Backend legacy test extended with the boolean case.
Judge whether the held-PUT test still proves ordering after
its restructure (validation asserted after restoring real
timers, before release). Still missing (admitted): legacy-GET
remount sequence at page level; fresh-module new-tab tests;
Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 353 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- `pytest tests/test_gap_completion.py`: 24 passed. Full
  backend suite not repeated (backend change is the `_is_int`
  guard; round-eight full run: 911 passed / 5 named failures).
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

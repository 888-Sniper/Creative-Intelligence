# Creative Intelligence — audit of the fifteenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `bf0556f8a3263e4a3b2719733dcf2fefbcb2f73d`
  (code `01102ea` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `573b2ac2517716ed2f04b2a556e91eda47b99254`
  (`Fix the fifteenth-round audit defect (generation-stamped save outcomes)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `573b2ac` on this push touch only this `Audit.md`;
  review the code at `573b2ac` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat bf0556f8a3263e4a3b2719733dcf2fefbcb2f73d 573b2ac2517716ed2f04b2a556e91eda47b99254
git diff bf0556f8a3263e4a3b2719733dcf2fefbcb2f73d 573b2ac2517716ed2f04b2a556e91eda47b99254
git rev-parse 573b2ac2517716ed2f04b2a556e91eda47b99254    # must resolve
git diff --stat 573b2ac2517716ed2f04b2a556e91eda47b99254 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 2 files, 84 insertions, 9
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 573b2ac:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show bf0556f:Audit.md`,
parent `d97fd3b`, code `01102ea`). This push answers the
fifteenth review of `01102ea` (one P2 defect); re-verify it
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `573b2ac`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `573b2ac`,
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

1. `Fifteenth-review defect` — verdict with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. An older success cannot erase a newer synchronous failure

Claim. Save outcomes are stamped with their commit generation
(`saveOutcomeRef`/`recordSaveOutcome`, `SettingsPage.tsx`):
recording is unconditional in settle order, but a settle whose
generation is older than the recorded outcome cannot overwrite
it — including a synchronous local-storage failure recorded by
a newer commit while the older write was in flight. Try:
gen2 storage-failure, then gen1 success, then gen3 Retry
success (outcome clearing + status path); gen2 storage-failure
whose queued keys ride gen1's in-flight batch (batch timing:
taken before vs after gen2 queued — what does each settle
record, and can the visible error outlive the server actually
holding the change?); validation restoring "error" from a
failure whose keys a later flush already confirmed (can
`saveOutcomeRef.failed` be true while pending is empty?);
account switch remount (per-mount outcome ref, module-level
pending — owed anything?).

### 2. Debounce guard no longer depends on render timing

Claim. `onWorkspaceInput` mirrors the draft into
`nameDraftRef` synchronously, so the timer's supersede check
cannot read a render-lagged old name. Try: every other reader
of `nameDraftRef` (reconcile typing check, settle draft check,
unmount flush, GET-merge preconditions, identity-adopt
branch) under the earlier-visible value; Reset's
`setNameDraft` without a synchronous ref write (its timer is
cleared explicitly — verify no other path re-arms it).

### 3. Tests

Claims. New test drives the reviewer's exact sequence with a
held PUT: density in flight → accent commit under throwing
storage (Retry visible) → older PUT succeeds → name cleared →
validation still shows Retry/error, and Retry then flushes
the stranded accent. Flake disclosure: during development the
full suite twice failed ONE pre-existing test
(`validates the workspace name instead of saving blanks`,
error text never appeared, status stuck Saving) while it
passed in isolation and in the final runs (356 passed). The
implementer attributes it to the render-lagged ref in claim 2
under parallel load and fixed that mechanism — judge whether
that explanation holds from source, and whether other
fake-timer tests share the hazard. Still missing (admitted):
legacy-GET remount at page level; fresh-module new-tab tests;
Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 356 passed (final run; see flake disclosure).
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

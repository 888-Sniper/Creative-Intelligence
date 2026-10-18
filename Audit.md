# Creative Intelligence — audit of the eighth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `018a937782330cbd6e5eda98af0f530dd9823d52`
  (code `06a8fa7` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `63020ee718c0b4836c773628ed4753e9a00ec4b1`
  (`Fix the eighth-round audit defects (preference conflicts, filter clears)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `63020ee` on this push touch only this `Audit.md`;
  review the code at `63020ee` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 018a937782330cbd6e5eda98af0f530dd9823d52 63020ee718c0b4836c773628ed4753e9a00ec4b1
git diff 018a937782330cbd6e5eda98af0f530dd9823d52 63020ee718c0b4836c773628ed4753e9a00ec4b1
git rev-parse 63020ee718c0b4836c773628ed4753e9a00ec4b1    # must resolve
git diff --stat 63020ee718c0b4836c773628ed4753e9a00ec4b1 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 15 files, 410 insertions, 41
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 63020ee:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show 018a937:Audit.md`, parent `55b4c96`, code `06a8fa7`).
This push answers the eighth review of `06a8fa7` (defects 1–3);
re-verify those first, then hunt wider. Earlier rounds' fixed
items should be regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `63020ee`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `63020ee`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each of the eighth review's 3 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Eighth-review 3 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Stale preference saves are explicit conflicts, reconciled before "saved"

Claim. `save_prefs` raises `StalePreferenceRevision` (carrying the
current prefs) instead of returning success
(`Backend/creative_intel/notifications.py`); `PUT /api/preferences`
answers 409 with `{error, prefs}` (flat body — the app strips
FastAPI's `detail` envelope, `Backend/ci_backend/app.py`).
Settings retries once on the fresh base and shows "saved" only
after acceptance; the optimistic immediate "saved" and the
earlier-commit-completion flash are gone (`SettingsPage.tsx`,
`commitRev` guard). Try: a second consecutive 409 (three tabs);
409 without `prefs` (account mismatch) proving no retry loop;
retry succeeding but the OTHER keys in the conflict body being
adopted as snapshot without the UI showing them (local UI now
diverges from snapshot — what does the next delta do?); a failed
LOCAL save followed by Retry (`retrySave` re-commits identical
prefs — delta vs snapshot must still contain the unsaved keys).

### 2. One tab cannot overwrite another tab's unrelated edits

Claim. Each tab keeps its own confirmed server snapshot
(`noteServerPrefsSnapshot`/`serverPrefsSnapshot`, `prefs.ts`);
saves send ONLY `serverPrefsDelta(snapshot, next)` with the
snapshot's version as base. Delta is computed at queue execution
time (edit-then-revert lands correctly) but fixed before the
first attempt (conflict retry reuses it verbatim). Try: partial
server documents (keys absent from the snapshot are sent — can
that clobber anything?); a GET merge landing while a PUT is
queued (rev guards in Settings/AppShell vs the snapshot note
order — snapshot is noted BEFORE the local merge applies; find a
sequence where local prefs and snapshot disagree and a delta
then restores a stale value); Reset Defaults under delta
semantics (a key another tab changed that this tab's snapshot
already holds at default is NOT reset — is that the right
reading of "reset"?); two Settings mounts in one tab sharing the
module queue/snapshot after account switch (snapshot keyed by
employee — verify every read/write uses the same id source).

### 3. Every shared filter clear records the explicit All status

Claim. `FilterContext.clearFilters` itself marks
`touched = ""` for the current account (choke point), covering
Analyst Clear All, FilterBar, Dashboard/Benchmarks/Creatives
resets and `product.tsx` buttons. Analyst conversation restore
re-marks AFTER its clear+set sequence; `SampleScopeBanner`
captures the pre-demo touched state (`prevStatusTouched`,
including "was untouched") and restores it on return via the new
`clearCampaignStatusTouched`. Try: clears fired before identity
loads (employee id `""` in FilterProvider vs the real id
Campaigns reads — is the app reachable pre-identity?);
SampleScopeBanner mounting in that same window (its apply
effect captures the id from first render); saved-view applies
and other programmatic `setFilter("status", …)` writers that
bypass marking entirely; Campaigns' own status `<select>`
onChange vs the choke point disagreeing after a clear on the
Campaigns page itself.

### 4. Drive-by: pre-existing video journey test fixed

Claim. `test_positive_journey_analysis_correction_review_export`
failed IDENTICALLY on the untouched parent (`TypeError`:
`LiveVision` test double rejects the `secret_for` kwarg added in
round two). The double now accepts and ignores it
(`tests/test_video_upload_api.py`). Verify the base failure
yourself from history if you doubt it, and check no other test
double in the tree stubs `LiveVision`/`readiness` with a stale
signature.

### 5. Tests

Claims. Backend: stale save now asserted to RAISE with current
prefs attached; new HTTP two-tab test (B saves → A 409 with B's
prefs in body → A retry → both edits survive, nothing written by
the rejected save). Frontend: Settings conflict test drives the
real fetch mock (stateful merge-apply server) and asserts both
PUT bodies (bases 3→9, prefs exactly `{theme}`); edit-then-
revert lands `{theme: "light"}`; server-500 never shows saved;
`serverPrefsDelta` unit tests; FilterContext clear test. Two
partial `@/auth/AuthProvider` mocks (Dashboard, VideoUpload)
gained the `useOptionalAuth` export FilterContext now uses —
check no other test mock of that module is incomplete. Still
missing (admitted): a page-level Analyst-Clear-All → Campaigns
navigation test (mechanism covered at FilterContext level), and
the previously flaky Settings storage test passed throughout
this round (full suite + isolated) — its timing dependency is
still unexplained.

## Evidence (implementer's machine; check plausibility, do not re-run)

- FULL backend suite run this round: 911 passed, 1 skipped,
  6 failed — the five named pre-existing failures plus the
  video-journey double above (proven failing on the stashed
  untouched tree, then fixed; the single test passes after).
  `pytest tests/test_gap_completion.py`: 23 passed.
- `pnpm test`: 338 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- Ruff on changed Python: 20 errors, ALL pre-existing import
  sorting in `product.py` (identical count on `git show
  HEAD:` content); none in the edited regions or new code.
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

# Creative Intelligence — audit of the sixth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `422f8db5dcc45433988dcf0809c19b45e1dbfcaa`
  (code `965158f` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `b33cc7a035f176e15d0c8e958af0572cb67dbd03`
  (`Fix the sixth-round audit defects (dashboard basis, touched value, stale saves)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `b33cc7a` on this push touch only this `Audit.md`;
  review the code at `b33cc7a` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 422f8db5dcc45433988dcf0809c19b45e1dbfcaa b33cc7a035f176e15d0c8e958af0572cb67dbd03
git diff 422f8db5dcc45433988dcf0809c19b45e1dbfcaa b33cc7a035f176e15d0c8e958af0572cb67dbd03
git rev-parse b33cc7a035f176e15d0c8e958af0572cb67dbd03    # must resolve
git diff --stat b33cc7a035f176e15d0c8e958af0572cb67dbd03 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 10 files, 145 insertions, 27
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show b33cc7a:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show 422f8db:Audit.md`, parent `f41c759`, code `3d9e4d8`).
This push answers the sixth review of `965158f` (defects 1–4 plus
the test-coverage note); re-verify those first, then hunt wider.
Earlier rounds' fixed items should be regression-checked, not
re-reported unless broken again.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `b33cc7a`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `b33cc7a`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end.
- For each of the sixth review's 4 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Sixth-review 4 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Dashboard basis request is valid and reactive

Claim. The unrestricted basis fetch uses `days=180` (backend
`benchmarks.daily_points` accepts 1–180; 180 covers the 90-day
saved maximum). When the basis lands after a scoped-fallback boot,
an effect recomputes the window while untouched. `bootedMode`
distinguishes automatic All Time from finite: a late finite
preference applies after automatic All Time (guarded by
`userDateTouched`, set whenever visible dates leave the booted
state). The Dashboard test mock now enforces the real 1–180
contract. Try: datasets longer than 180 days (basis truncated —
does a 90-day slice still end at the true last date?); basis
fetch failing then prefs landing; explicit user clear-to-empty
after finite boot (touched marking via the finite branch);
`applyRangeBoot` identity changing every render causing looped
recomputes; sample-scope (`ci-sample-batch`) interplay.

### 2. Campaign status flag and value travel together, per account

Claim. `markCampaignStatusTouched(id, value)` /
`touchedCampaignStatus(id)` (`state/prefs.ts`) store the chosen
value in sessionStorage + memory, keyed by employee. Campaigns
restores the value when filters are empty (reload case) and never
applies the saved default over a touched account. Analyst passes
the restored status value. Try: legacy `"1"` entries; choosing
"All" explicitly (value `""` stored as `"1"` — restored as touched
with no value: correct or stranded?); A→B→A in one tab; status
set by saved views/deep links/other pages (still unmarked — can
the default override those?); empty employee id key sharing.

### 3. Preference saves are serialized and revision-checked

Claim. Settings PUTs chain through `putServerPrefs` (module
promise chain) in edit order, each carrying
`currentPrefsRevision()`; `notifications.save_prefs(...,
revision=…)` stores `_rev` monotonically and returns the existing
prefs unchanged for stale revisions. `test_stale_preference_revision_cannot_overwrite`
covers old-loses/newer-wins. Try: two tabs (revisions are per-tab
counters — cross-tab stale writes?); reset spam clicking; PUT
failure mid-chain poisoning later saves; `_rev` leaking into
client-visible prefs merges (`mergeServerPrefs` allowlist drops
it — verify); non-integer revision handling; AppShell's own
savePrefs-on-merge bumping revision without a PUT (server `_rev`
vs client counter drift).

### 4. Coverage note

Claim. Added: backend stale-revision test (above), prefs.test
value-travel assertions, Dashboard mock contract enforcement.
Still missing (admitted): full page-level UI tests for delayed
range transitions, account switching with server prefs in flight,
and reset-across-reload. Judge whether the remaining risk needs
them before calling this complete, and name the exact test you
would add for any gap you keep open.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 21 passed.
- `pnpm test`: 330 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- Backend production change is confined to `notifications.py`
  (revision check) + one router line; full 899-test run remains
  unrepeated since the first push.
- Gemini key re-probed: still absent; user previously chose
  "skip live run". Live workflow remains unverified.

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

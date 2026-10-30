# Creative Intelligence — audit of the checkpoint-036 incremental push

You are the second, independent reviewer. Find what is still missing, wrong,
or unsafe below. Assume every claim is unproven until you have opened the
cited code and tried to falsify it. Do not call the product perfect and do
not repeat the implementer's summary as your own finding. This push does
not complete the audit or the remediation: most groups remain open below.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Original audited pin / parent: `1342bb48ef59c45981c716c77d12898ae029daba`
- Code under review: `b690c69c2a8b64e69e192ad394818fbc10636724`.
  Commits after that code head on this push touch only this `Audit.md`.
  Review the code regardless of branch head. After `git fetch`, confirm
  with `git rev-parse origin/main`.
- Provenance: saved cloud implementation `fa30fc21e897a832b3358d851555385530b5d2e4`
  (tree `b3d4d169f9ecc920bfbd75ff63b0b0cb674d12eb`, 34 commits) was imported
  as a zero-context patch, Mac commit `1ba11abe2b011f880b0adcbd603c1a09bfd3da29`.
  Commit identity was not recreated. Later Mac commits:
  `58251b1fd655fe756474429b9cd218c0affc040b` (legacy-scope triage),
  `4c3344a05a7550e5c62177b892f428d47b41e6ac` (QI323),
  `7bce053a8c4ec85befe80644764d114c31afe15b` (QI176 slice),
  `06d163daaab3ce15c8ef7cc78e8f9839d3348b2e` (QI124/QI126),
  `8305af3fa1ab2561da9bff20c9f95b9c34eaa8f1` (Mac re-audit fixes),
  `c0eaf8afb41894658b4e22413bc77bf6eff1dff0` (verifier nits), then checkpoint-032 commits `432ab38` (daily/filtered/QA), `0772b15` (Compare/Campaigns), `2f3e98b` (QI270 tests), `e3af84b` (032 re-audit crash/cross-currency fixes), `c020e60` (Audit.md only), `ccfe325` (QI-004 comma campaign names and QI-195 Ask scope), `99ddf02` (Audit.md only), `e9d4f0a` (QI-006 daily-series failures and QI-009 panel failures), `b35d549` (Audit.md only), `d7b4c5e` (QI043 compare-option failures and QI045 filter metadata), `92edef8` (Audit.md only). This push's code commit is `b690c69` (QI-001, QI035, QI036, QI037, QI038, QI172, QI173 with QI259, QI178, QI263, QI315). Previous main was `92edef8`.
- Render auto-deploys from `main`. Deployment of this push was not
  verified when this file was written. Do not treat live-site state as
  a source defect.

Confirm with both ends named (never a one-revision diff):

```
git fetch origin
git diff --stat 92edef89686cdfe2a638a91d341c0ee27b756d71 origin/main
git diff 92edef89686cdfe2a638a91d341c0ee27b756d71 origin/main
git diff --stat 92edef89686cdfe2a638a91d341c0ee27b756d71 b690c69c2a8b64e69e192ad394818fbc10636724
git diff --stat b690c69c2a8b64e69e192ad394818fbc10636724 origin/main
git rev-parse origin/main
git status  # stop only if dirty, or origin/main differs from GitHub main
```

The commit under review is `origin/main` after fetch. Previous main is
`92edef89686cdfe2a638a91d341c0ee27b756d71`. The first diff is the whole
push: the code below plus this file. The code slice
`92edef8`..`b690c69` is 10 files, 993 insertions, 171 deletions.
`b690c69`..`origin/main` is this file only. If yours disagrees, stop
and say so. A behind checkout or
no local `main` branch is not a reason to stop. Read files at the reviewed
commit; if a line moved, follow the symbol. Original audit scope was
incomplete (51,371 of 103,845 lines scored); unscored scope may hide more.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or activate
  a provider. Read-only inspection only (test *reading* is required; do
  not re-run suites as proof — judge the recorded commands and code).
- Report ONLY defects still true at the code head, each with severity,
  observed behavior, exact file and line, and evidence. No evidence:
  use "Unverified". Respect deferred-source boundaries in the handoff
  ledger: do not demand display of withheld mixed-owner lines.
- Do NOT treat as source defects: unrun live provider calls, unrun live
  browser/Render checks, missing console credentials, the four
  pre-existing failures named under Evidence, or any still-open group
  listed below (re-report only if this push made it worse).
- Check tests as skeptically as code. Secrets: file/line only, redacted.

## Required output format

1. `Claims check` — one verdict line per implemented/partial group below.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found`.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## Counting (do not double-count)

335 original finding entries reconcile into 326 planning groups (9
consolidations: QI303→QI-011, QI259→QI173, QI270→QI269, QI280→QI189,
QI308→QI307, QI095→QI016, QI101→QI060, QI228→QI251, QI302→QI312).
Groups are not unique runtime-reproduced bugs. Kinds: 193 defects,
36 conditional risks, 45 test gaps, 52 improvements. Severity: 0 critical,
37 high, 193 medium, 96 low. Status at this push: 48 implemented pending
your verification, 6 partial, 272 untouched. Nothing below erases an
unresolved finding, and implemented does not mean verified by you.

## This push

Parent `92edef89686cdfe2a638a91d341c0ee27b756d71`. Code
`b690c69c2a8b64e69e192ad394818fbc10636724`. These ten groups are
implemented pending your verification. They are not verified. QI259
is the supporting test gap inside QI173, not a second group. No UI
file changed. `en.ts` was not edited.

QI-001, high, defect. A stored video-only snapshot rebinds with
`video_only=True`. `review_bind.stored_video_only` is true only when
the saved snapshot says so. `product.py` passes that flag into
`bind_snapshot` (around line 2442) and compares `review_bind.SNAPSHOT_KEYS`,
which includes `video_only`. `bind_snapshot` with `video_only=True`
returns empty `records` and does not require a confirmed destination
(`video_analysis.py` around lines 269–274). The default combined call
still raises `AnalysisUnavailable` without that destination.
`inputs_unchanged` treats a missing `video_only` as equal to false,
and an explicit true as different from false. Do not call the review
route. Confirm with `test_video_only_bind_needs_no_destination`,
`test_video_only_flag_compares_without_treating_legacy_as_a_change`,
and `test_review_rebind_passes_the_stored_video_only_flag`.

QI035, high, defect. `_ALIASES` values are ordered tuples. The first
alias is canonical and reserved for that field. `clicks` keeps
`link clicks` last (`ingest.py` around line 73), so a file with both
Clicks and Link Clicks maps each to its own field, and a Link
Clicks-only file still fills clicks. Two columns for one field with
unequal non-blank values quarantine the row (`_header_conflict`,
around line 363) with reason `ambiguous {field}`. Agreeing duplicates
keep the earlier column and record the ambiguity. Duplicate raw
headers are recorded as `duplicate headers`. Confirm with
`test_both_click_columns_stay_on_their_fields`,
`test_link_clicks_only_still_fills_clicks`,
`test_disagreeing_spend_columns_are_quarantined`, and
`test_agreeing_spend_columns_keep_the_first_and_record_ambiguity`.

QI036, high, defect. A blank, `-`, `n/a`, `N/A`, or `brak` revenue
cell sets `revenue_reported` false (`ingest.py` around lines 416 and
428). A numeric zero stays reported. An unmapped revenue column stays
unreported. `benchmarks.matched_roas` then uses only reported rows:
100 spend with revenue 200 plus 900 spend with `brak` is ROAS 2.0
at coverage 0.1. Confirm with
`test_blank_revenue_markers_stay_unreported_and_zero_stays_reported`
and `test_matched_roas_uses_only_reported_revenue`.

QI037, high, conditional risk. `record_import` and `upsert_rows`
take `commit=False` inside both `import_report` and
`import_xlsx_report`. One count update and one commit follow. An
exception rolls the facts and the provenance row back together
(`ingest.py` `import_report` around lines 788–801). Confirm with
`test_import_count_failure_rolls_back_facts_and_provenance` and
`test_commit_false_rolls_back_and_default_upsert_commits`.

QI038, high, defect. Each quartile point divides by the impressions
of rows that reported that quartile (`retention.py` `impr_q`, point
loop around lines 94–108), and stores `coverage` as that exposure
over total impressions. A measured zero stays 0. A wholly missing
quartile adds no point. `schema.migrate` adds nullable `coverage`
beside the existing source column (around lines 650–651) and does
not add an Alembic revision. Confirm with
`test_partial_quartile_uses_reporting_impressions_only`,
`test_measured_zero_quartile_stays_zero`, and
`test_wholly_missing_quartile_adds_no_point`. The older quartile
curve tests in `test_acceptance_10.py` still expect 80% when the
only row reports the quartile.

QI172, high, defect. When the early and late product-timing groups
use different rate labels and both rates exist, `qa.answer` says
the rates are not comparable and does not emit a yes/no numeric
verdict (`qa.py` around lines 772–777). Both-completion and
both-play comparisons stay numeric. Confirm with
`test_early_completions_and_late_plays_are_not_ranked` and
`test_early_plays_and_late_completions_are_not_ranked`.
`BackendVtrTest` still expects 36.7% vs 20.0% play rate and
10.0% vs 6.7% VTR.

QI173, high, defect, with QI259. `_cpa` returns no value when
conversions are zero (`qa.py` around line 101). Format prose says
`CPA unavailable` (around line 823). Zero impressions say
`Blended CTR is unavailable` (around line 597) and do not say
`0.00%` or `300.00%`. Positive impressions with zero clicks still
say `0.00%`. Confirm with
`test_zero_conversion_format_cpa_is_unavailable`,
`test_zero_impression_ctr_is_unavailable_and_zero_clicks_stay_zero`,
and `test_mvp.py` `test_ctr_zero_impressions_reports_zero_not_clicks`.
`BackendTiktokTest` still expects `CPA $10.00` and `CPA $20.00`
when conversions exist.

QI178, high, defect. Top-versus-bottom groups rank by
`_question_metric` (`qa.py` around lines 991–1014), not by the
fact-pack CPA score. Lower CPA is better. Other rates are
higher-better. Unnamed ranking uses spend. Fewer than two scored
keys says there are not enough ranked creatives. Confirm with
`test_top_and_bottom_follow_ctr_when_cpa_ranks_the_other_way`:
creatives 10 and 9 lead CTR, and creatives 1 and 2 lead the low
CPA that the question did not ask for. `test_acceptance_10.py`
`test_top_vs_bottom` still expects `Top 20%` and `Bottom 20%`.

QI263, high, conditional risk. `recovery_due` decides from a
monotonic deadline whether the loop should scan. Both `daemon` and
`main` call it and then `recover_expired_leases` (`worker.py`
around lines 126–138, 164–175, and 207–218). A fresh lease stays
running. An expired lease is requeued once the deadline is due.
A call before the deadline does not scan. Do not start `daemon`
or `main`. Confirm with
`test_recovery_due_uses_the_monotonic_deadline`,
`test_expired_lease_requeues_once_and_a_fresh_lease_stays`, and
`test_both_loops_recheck_recovery_due`.

QI315, high, conditional risk. `docs/BACKUP.md` Restore (around
lines 106–156) requires a nonempty backup, a readable database,
and a readable media directory, copies both into
`<data>/.restore-staging`, checks the copies, keeps the current
database and media as `<data>/.restore-rollback`, and only then
switches the staged pair. The old order that copied the backup
database onto the live database and then deleted live media is
absent. This is documentation. Do not run it. Confirm with
`test_restore_doc_stages_and_keeps_a_rollback_copy`.

QI043 and QI045 stay pending from `d7b4c5e` and were not re-edited.
QI044 stays untouched. The six partials are unchanged: QI016,
QI017, QI028, QI057, QI150, and QI176.

## Claims to falsify — implemented pending verification (48; the ten highs above are this push, prior 38 already on main)

For checkpoint-030 groups, the Mac tree commit is the import commit
`1ba11ab…` (historical batch commit in parentheses). Benefit is the
finding's intended benefit; verify the code actually delivers it.

### QI-001 — Video-only analysis cannot finish the normal review workflow

- Findings: QI-001; severity high; kind defect.
- Original locations (pin `1342bb4`): the review rebind required a combined-analysis destination.
- Files now: `Backend/creative_intel/review_bind.py`; `Backend/ci_backend/routers/product.py` around line 2442; `Backend/creative_intel/video_analysis.py` `bind_snapshot` around lines 269–274.
- Change (`b690c69`): a stored video-only snapshot rebinds in video-only mode. A missing flag still matches an older combined snapshot. An explicit mode change still fails the snapshot compare.
- Benefit to verify: a video-only review can finish without a combined destination, and a mode or revision mismatch still refuses.
- Status: implemented pending verification (not verified).

### QI035 — Header aliases pick conflicting columns in unordered set order

- Findings: QI035; severity high; kind defect.
- Original locations (pin `1342bb4`): `_ALIASES` used sets, so the same header could land on more than one field.
- Files now: `Backend/creative_intel/ingest.py` `_ALIASES` around line 73, `_map_headers` around line 308, `_header_conflict` around line 363.
- Change (`b690c69`): alias order is the precedence. A canonical header is reserved. Disagreeing same-field columns quarantine the row.
- Benefit to verify: conflicting report headers import deterministically, and disagreeing same-field columns are quarantined. A Link Clicks-only export still fills clicks.
- Status: implemented pending verification (not verified).

### QI036 — A missing revenue marker can be flagged as a reported zero

- Findings: QI036; severity high; kind defect.
- Original locations (pin `1342bb4`): blank revenue could be stored as a reported zero and enter ROAS.
- Files now: `Backend/creative_intel/ingest.py` around lines 416 and 428; `benchmarks.matched_roas`.
- Change (`b690c69`): blank markers and an unmapped revenue column set `revenue_reported` false. Numeric zero stays reported.
- Benefit to verify: missing revenue stays out of ROAS, and a real zero stays reported.
- Status: implemented pending verification (not verified).

### QI037 — Import facts and provenance counts commit in separate transactions

- Findings: QI037; severity high; kind conditional risk.
- Original locations (pin `1342bb4`): `record_import` and the ads upsert committed before the count update.
- Files now: `Backend/creative_intel/ingest.py` `import_report` around lines 788–801 and the matching xlsx path.
- Change (`b690c69`): facts and the import row commit together. A failure on the count update rolls both back.
- Benefit to verify: an import either commits facts and counts together or rolls back.
- Status: implemented pending verification (not verified).

### QI038 — Synthetic retention divides reported quartiles by unreported exposure

- Findings: QI038; severity high; kind defect.
- Original locations (pin `1342bb4`): quartile percent used every impression, including rows that did not report that quartile.
- Files now: `Backend/creative_intel/retention.py` around lines 94–108; `Backend/creative_intel/schema.py` around lines 650–651.
- Change (`b690c69`): the denominator is the impressions that reported the quartile. Coverage is stored. A missing quartile adds no point.
- Benefit to verify: a partly reported quartile uses only the impressions that reported it, and coverage is stored.
- Status: implemented pending verification (not verified).

### QI172 — QA compares completion rate with play rate across different timing measures

- Findings: QI172; severity high; kind defect.
- Original locations (pin `1342bb4`): `qa.answer` compared early and late rates even when one side was completions and the other was plays.
- Files now: `Backend/creative_intel/qa.py` around lines 772–777.
- Change (`b690c69`): different labels with both rates present produce an incomparable sentence and no yes/no numeric verdict.
- Benefit to verify: QA does not rank completion rate against play rate.
- Status: implemented pending verification (not verified).

### QI173 — QA renders unavailable CTR and format CPA as measured zeroes

- Findings: QI173, QI259; severity high; kind defect. QI259 is the test gap for this formatter, not a separate group.
- Original locations (pin `1342bb4`): zero impressions rendered CTR as 0.00%, and zero conversions rendered format CPA as $0.00.
- Files now: `Backend/creative_intel/qa.py` `_cpa` around line 101, CTR text around line 597, format CPA around line 823; `tests/test_mvp.py`.
- Change (`b690c69`): unavailable CTR and zero-conversion CPA say unavailable. A measured zero click rate on positive impressions stays 0.00%.
- Benefit to verify: QA does not print unavailable CTR or zero-conversion CPA as a measured zero.
- Status: implemented pending verification (not verified).

### QI178 — QA top-versus-bottom groups ignore the requested ranking metric

- Findings: QI178; severity high; kind defect.
- Original locations (pin `1342bb4`): the top-versus-bottom block used the fact-pack CPA ranking.
- Files now: `Backend/creative_intel/qa.py` around lines 991–1014. `_fact_pack` scoring was not changed.
- Change (`b690c69`): the answer ranks those groups by the metric named in the question. Unnamed questions rank by spend.
- Benefit to verify: top and bottom groups follow the metric the question named.
- Status: implemented pending verification (not verified).

### QI263 — A job whose lease expires after the worker starts is not recovered by the polling loop

- Findings: QI263; severity high; kind conditional risk.
- Original locations (pin `1342bb4`): lease recovery ran once at startup.
- Files now: `Backend/ci_backend/worker.py` `recovery_due` around line 126, called from `daemon` and `main`.
- Change (`b690c69`): each poll rechecks a monotonic deadline and requeues expired leases. A fresh lease is left running. The tests do not start the worker.
- Benefit to verify: a polling worker rechecks expired leases without another process start and leaves fresh leases alone.
- Status: implemented pending verification (not verified).

### QI315 — A manual restore replaces current data before the replacement is validated

- Findings: QI315; severity high; kind conditional risk.
- Original locations (pin `1342bb4`): `docs/BACKUP.md` copied the backup onto the live database and then deleted live media.
- Files now: `docs/BACKUP.md` Restore, around lines 106–156.
- Change (`b690c69`): the guide stages and checks the replacement, keeps a rollback copy, and only then switches. It is documentation and was not executed.
- Benefit to verify: the manual restore guide stages and keeps a rollback copy before replacing current data.
- Status: implemented pending verification (not verified).

### QI043 — Failed comparison options become an impossible selection instruction

- Findings: QI043; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): `ComparePage.tsx` treated a failed option request as an incomplete selection.
- Files now: `apps/creative-intelligence-ui/src/pages/ComparePage.tsx`.
- Change (`d7b4c5e`): the active catalogue error renders with Retry. Empty and one-option successes keep their existing copy.
- Benefit to verify: A failed option load is distinct from no campaigns and from an unfinished pick, and Retry can restore the catalogue.
- Status: implemented pending verification (not verified).

### QI045 — Filter panels hide metadata failures as empty option lists

- Findings: QI045; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): `product.tsx` `FilterPanel` derived options only from metadata data.
- Files now: `apps/creative-intelligence-ui/src/components/product.tsx` (`FilterPanel`, `useCampaignMeta`).
- Change (`d7b4c5e`): a metadata error shows the API message and Retry. Current selections stay. An empty successful list stays empty without Retry.
- Benefit to verify: A failed metadata fetch is visible and recoverable, and it does not wipe the filters the person already set.
- Status: implemented pending verification (not verified).

### QI-006 — Daily-series request failures are presented as an empty dataset

- Findings: QI-006; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): `apps/creative-intelligence-ui/src/components/product.tsx` `useDaily` catch stored `[]`.
- Files now: `apps/creative-intelligence-ui/src/components/product.tsx` (`useDaily`); `pages/DashboardPage.tsx`; `pages/CampaignsPage.tsx`; `pages/AskPage.tsx`.
- Change (`e9d4f0a`): `useDaily` returns `{data, error, loading}`. Callers show the error before an empty series. A scope change hides the previous points. A successful empty array stays data.
- Benefit to verify: A failed daily request is distinct from no rows, and a retry does not require reloading the page.
- Status: implemented pending verification (not verified).

### QI-009 — Several analytics and preview panels retain loading visuals after failed requests

- Findings: QI-009; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): Dashboard, Campaigns, Creatives, Workbook fullscreen, and Ask platform context branched on data and otherwise kept a skeleton.
- Files now: `product.tsx` (`LoadError`); `DashboardPage.tsx`; `CampaignsPage.tsx`; `CreativesPage.tsx`; `WorkbookPage.tsx`; `AskPage.tsx`.
- Change (`e9d4f0a`): each named panel renders error, then loading, then loaded empty or populated. Retry bumps the existing refresh key, or Ask's own tick, or the workbook preview tick.
- Benefit to verify: A failed prerequisite shows the API error and a Retry control. A successful empty response still uses the existing empty copy.
- Status: implemented pending verification (not verified).

### QI-004 — Comma-delimited comparison selections cannot preserve campaign names containing commas

- Findings: QI-004; severity high; kind defect; workstream B2.
- Original locations (pin `1342bb4`): `savedViews.ts` compare link join; `ComparePage.tsx` campaign join and split; `actions.py` `_csv_param` via `expert2_compare_route`; `product.py` `",".join(body.campaigns)`.
- Files now: `apps/creative-intelligence-ui/src/components/compareSelection.ts`, `savedViews.ts`, `pages/ComparePage.tsx`, `Backend/ci_backend/actions.py` (`_selection_names`, `expert2_compare_route`), `Backend/ci_backend/routers/product.py` (compare post).
- Change (`ccfe325`): repeated query names and an intact JSON campaign list. Legacy single-value comma links still split after the framework decodes them.
- Benefit to verify: Saved links, direct comparisons, and JSON requests keep exact campaign identities, including a comma inside a name.
- Status: implemented pending verification (not verified).

### QI195 — Ask answers remain paired with newly filtered KPI context

- Findings: QI195; severity high; kind defect; workstream B2.
- Original locations (pin `1342bb4`): `apps/creative-intelligence-ui/src/pages/AskPage.tsx` answer install without a scope generation.
- Files now: `apps/creative-intelligence-ui/src/pages/AskPage.tsx` (`answerScopeKey`, `askGen`, the answer panel guard). Deferred line for the review-saved note was not edited.
- Change (`ccfe325`): the answer, its error, and its supporting visuals belong to the scope that asked. A later filter clears them. An older completion cannot publish or clear a newer request's busy flag.
- Benefit to verify: An answer and the KPI, trend, and benchmark context under it are one analytical scope.
- Status: implemented pending verification (not verified).

### QI-005 — A failed KPI refresh leaves prior-scope values displayed as current

- Findings: QI-005; severity high; kind defect; workstream B2.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/components/product.tsx:160-168.
- Files: apps/creative-intelligence-ui/src/components/product.tsx.
- Change (import `1ba11ab`, historical batch P16_kpi_refresh_state `97b6146`): KPI results now belong to the current memoized filter loader and explicit refresh; prior values/errors clear on loading/failure. API contracts unchanged; integration pending.
- Benefit to verify: Prevent users acting on another filter scope's KPI values and make refresh failures visible.
- Status: implemented pending verification (not verified).

### QI-007 — Top Performer benchmark uses the worst CPA/CPC value

- Findings: QI-007; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/DashboardPage.tsx:754-756.
- Files: apps/creative-intelligence-ui/src/pages/DashboardPage.tsx.
- Change (import `1ba11ab`, historical batch P02 `2740a3f`): See diff for listed files.
- Benefit to verify: Make performance reference comparisons follow each metric's actual direction.
- Status: implemented pending verification (not verified).

### QI014 — Creative deep links run CTR while the rank selector displays ROAS

- Findings: QI014; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/ComparePage.tsx:407-407.
- Files: apps/creative-intelligence-ui/src/pages/ComparePage.tsx.
- Change (import `1ba11ab`, historical batch P15_creative_boot_rank `ea6771f`): Initial creative comparison now uses the selector state used by Apply; only one production argument changes. Full application/backend integration pending.
- Benefit to verify: Make initial comparison winners reflect the displayed ranking choice.
- Status: implemented pending verification (not verified).

### QI015 — Fractional chart ticks are rounded into duplicate integer labels

- Findings: QI015; severity low; kind defect; workstream B4.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/components/charts.tsx:28-28.
- Files: apps/creative-intelligence-ui/src/components/charts.tsx.
- Change (import `1ba11ab`, historical batch P23_fractional_axis_labels `381491a`): Locale-aware fractional labels follow each axis interval. Local Intl/DOM tests pass; full-page/browser layout and independent review pending.
- Benefit to verify: Make small ratio and cost changes readable on the axis.
- Status: implemented pending verification (not verified).

### QI018 — Manual period comparison subtracts amounts in different currencies

- Findings: QI018; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/benchmarks.py:904-906.
- Files: Backend/creative_intel/benchmarks.py.
- Change (import `1ba11ab`, historical batch P08_manual_period_currency `1bce4fd`): Pure arithmetic and isolated table locally complete with preserved native values, localized reasons and defensive old-response handling; full integration/independent review pending.
- Benefit to verify: Suppress meaningless money deltas while keeping comparable non-money results.
- Status: implemented pending verification (not verified).

### QI019 — Missing prior measurements are described as measured zero

- Findings: QI019; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/period_compare.py:119-122; apps/creative-intelligence-ui/src/components/KpiTrend.tsx:200-205.
- Files: Backend/creative_intel/period_compare.py; apps/creative-intelligence-ui/src/components/KpiTrend.tsx.
- Change (import `1ba11ab`, historical batch P25_undefined_prior_comparison `fa30fc2`): Undefined prior values suppress comparison; genuine zero and measured deltas retain their behavior. Pure helper and unchanged UI verified in isolation; integration and independent review pending.
- Benefit to verify: Give trend badges an accurate reason for missing or undefined prior performance.
- Status: implemented pending verification (not verified).

### QI021 — Dashboard downsampling creates unequal totals under single-day labels

- Findings: QI021; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/DashboardPage.tsx:102-109.
- Files: apps/creative-intelligence-ui/src/pages/DashboardPage.tsx.
- Change (import `1ba11ab`, historical batch P24_daily_trend_observations `06619d7`): Exact permitted page projection and shared chart preserve daily values; full Dashboard/API/browser performance and independent review pending.
- Benefit to verify: Show a trend whose level is not an artifact of the final bucket length.
- Status: implemented pending verification (not verified).

### QI022 — Benchmark mini charts turn unavailable metrics into zero

- Findings: QI022; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx:447-447.
- Files: apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx.
- Change (import `1ba11ab`, historical batch P11_benchmark_values_and_missing_charts `e3ecb48`): Canonical values, native currencies and nullable chart slots corrected; exact source wiring preserved, full application/API/browser integration pending.
- Benefit to verify: Keep charts consistent with the table and avoid apparent free acquisitions.
- Status: implemented pending verification (not verified).

### QI023 — Benchmark group changes can preselect keys from the previous response

- Findings: QI023; severity medium; kind defect; workstream B2.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx:146-148.
- Files: apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx.
- Change (import `1ba11ab`, historical batch P17_benchmark_selection_ownership `24289a6`): Current grouping response owns selection initialization and pruning; requests hide old rows before effects. Full page and saved-view integration pending.
- Benefit to verify: Initialize and constrain selections against the current settled grouping response.
- Status: implemented pending verification (not verified).

### QI025 — Average watch time drops measured-zero rows from its denominator

- Findings: QI025; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:571-573.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P18_measured_zero_watch_time `6572350`): Measured-zero watch totals now retain their matching population and provenance; incompatible bases stay unavailable. QI026 and full integration remain pending.
- Benefit to verify: Stop overstating attention and preserve genuine all-zero measured results.
- Status: implemented pending verification (not verified).

### QI026 — Watch-time average fallback is unreachable when totals are absent

- Findings: QI026; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:557-562.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P19_reported_watch_average_fallback `3e69829`): Average-only rows now produce explicitly estimated, view-weighted results with provenance; measured totals keep priority. Full integration pending.
- Benefit to verify: Restore computable watch-time estimates with provenance.
- Status: implemented pending verification (not verified).

### QI027 — Pooled ratio repeatedly scans row lists quadratically

- Findings: QI027; severity medium; kind improvement; workstream B8.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:446-447.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P20_linear_pooled_ratio_availability `b9e225b`): Pooled-ratio eligibility avoids quadratic dictionary scans; output parity and bounded operation counts pass. No whole-application performance/integration assurance.
- Benefit to verify: A single eligible-row pass reduces unnecessary comparisons while preserving metric semantics.
- Status: implemented pending verification (not verified).

### QI030 — Period comparison results survive changes to the active filter scope

- Findings: QI030; severity high; kind defect; workstream B2.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/ComparePage.tsx:376-376; apps/creative-intelligence-ui/src/pages/ComparePage.tsx:434-437.
- Files: apps/creative-intelligence-ui/src/pages/ComparePage.tsx.
- Change (import `1ba11ab`, historical batch P14_manual_period_request_ownership `8658104`): Current key and invocation own manual period data/loading/errors; old completions cannot publish. Exact request expression unchanged; full application integration pending.
- Benefit to verify: Bind results to their request scope and prevent obsolete responses winning.
- Status: implemented pending verification (not verified).

### QI031 — Isolated trend points produce no visible SVG stroke

- Findings: QI031; severity medium; kind defect; workstream B4.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/components/charts.tsx:73-77.
- Files: apps/creative-intelligence-ui/src/components/charts.tsx.
- Change (import `1ba11ab`, historical batch P22_singleton_trend_observations `3d8249d`): Explicit point marks and local geometry/accessibility metadata verified in jsdom; browser/full-page integration and independent review pending.
- Benefit to verify: Render isolated observations without falsely connecting missing intervals.
- Status: implemented pending verification (not verified).

### QI033 — Frequency fallback combines all impressions with one partial reach row

- Findings: QI033; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:706-713.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P06_reported_populations `fe32add`): Both pure metric defects reproduced and locally fixed; full production caller/integration verification pending.
- Benefit to verify: Require matching population evidence before publishing frequency.
- Status: implemented pending verification (not verified).

### QI034 — Engagement pools numerator and denominator from different populations

- Findings: QI034; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:737-738; Backend/creative_intel/analyst_metrics.py:748-748.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P06_reported_populations `fe32add`): Both pure metric defects reproduced and locally fixed; full production caller/integration verification pending.
- Benefit to verify: Pool only matched observations with explicit partial-field coverage.
- Status: implemented pending verification (not verified).

### QI042 — Benchmark CPM bypasses the canonical mixed-currency result

- Findings: QI042; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx:263-263.
- Files: apps/creative-intelligence-ui/src/pages/BenchmarksPage.tsx.
- Change (import `1ba11ab`, historical batch P11_benchmark_values_and_missing_charts `e3ecb48`): Canonical values, native currencies and nullable chart slots corrected; exact source wiring preserved, full application/API/browser integration pending.
- Benefit to verify: Keep incomparable monetary metrics unavailable throughout tables and charts.
- Status: implemented pending verification (not verified).

### QI046 — Cost per thousand reached turns missing spend into measured zero

- Findings: QI046; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_metrics.py:666-666; Backend/creative_intel/analyst_metrics.py:674-675.
- Files: Backend/creative_intel/analyst_metrics.py.
- Change (import `1ba11ab`, historical batch P06_cost_per_reach_availability `cdd27c4`): Pure metric defect reproduced and locally fixed; production caller/integration verification pending.
- Benefit to verify: Require matching supplied spend and reach and preserve real zero costs.
- Status: implemented pending verification (not verified).

### QI049 — Format recommendations do not reverse when the other group wins

- Findings: QI049; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_diagnostics.py:1070-1076; Backend/creative_intel/analyst_diagnostics.py:1109-1110.
- Files: Backend/creative_intel/analyst_diagnostics.py.
- Change (import `1ba11ab`, historical batch P06_format_recommendation_direction `e447806`): Local policy reproduced and fixed in both directions; full Analyst delivery and independent review pending.
- Benefit to verify: Select recommendation wording using the same direction as winner identification.
- Status: implemented pending verification (not verified).

### QI050 — Positive diagnostic findings turn a layer into a concern

- Findings: QI050; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_diagnostics.py:1193-1195; Backend/creative_intel/analyst_diagnostics.py:1212-1213.
- Files: Backend/creative_intel/analyst_diagnostics.py.
- Change (import `1ba11ab`, historical batch P07_diagnostic_polarity `f3613d5`): Four named positive rules reproduced and corrected; all local rule families labelled; full Analyst/legacy integration and independent review pending.
- Benefit to verify: Carry explicit polarity so summary status agrees with the evidence.
- Status: implemented pending verification (not verified).

### QI052 — Daily scale diagnostics can compare money amounts in different currencies

- Findings: QI052; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst.py:208-215; Backend/creative_intel/analyst_diagnostics.py:788-791.
- Files: Backend/creative_intel/analyst.py; Backend/creative_intel/analyst_diagnostics.py.
- Change (import `1ba11ab`, historical batch P13_daily_scale_currency_scope `26de46d`): Daily native units and measured spend carried through producer/consumer; invalid monetary endpoints abstain while dimensionless fatigue continues. Full campaign integration pending.
- Benefit to verify: Require comparable currency and measured-spend provenance across time.
- Status: implemented pending verification (not verified).

### QI097 — Selecting Custom Range sends NaN into the shared date helper

- Findings: QI097; severity high; kind defect; workstream B2.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/AnalystPage.tsx:1191-1192.
- Files: apps/creative-intelligence-ui/src/pages/AnalystPage.tsx.
- Change (import `1ba11ab`, historical batch P01 `65903a3`): See diff for listed files.
- Benefit to verify: Handle custom range explicitly and reject invalid numerical presets defensively.
- Status: implemented pending verification (not verified).

### QI098 — Top Creatives does not implement its advertised ROAS-then-CTR ordering

- Findings: QI098; severity medium; kind defect; workstream B1.
- Original locations (pin `1342bb4`): apps/creative-intelligence-ui/src/pages/AnalystPage.tsx:999-1000.
- Files: apps/creative-intelligence-ui/src/pages/AnalystPage.tsx.
- Change (import `1ba11ab`, historical batch P02 `2740a3f`): See diff for listed files.
- Benefit to verify: Implement a deterministic, documented lexicographic ranking.
- Status: implemented pending verification (not verified).

### QI117 — The weak-hold worksheet rule compares 3-second hook against the 2-second benchmark

- Findings: QI117; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_workbook.py:219-219.
- Files: Backend/creative_intel/analyst_workbook.py.
- Change (import `1ba11ab`, historical batch P09_worksheet_hook_benchmark `75c103d`): Local generated formulas match their own numeric benchmarks; native spreadsheet/export and independent integration review pending.
- Benefit to verify: Select the matching benchmark from a shared metric-to-row mapping.
- Status: implemented pending verification (not verified).

### QI118 — Pooled workbook hold includes durations rejected by the per-creative formula

- Findings: QI118; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_workbook.py:178-179.
- Files: Backend/creative_intel/analyst_workbook.py.
- Change (import `1ba11ab`, historical batch P10_worksheet_hold_population `9e02f54`): Both pooled sums reuse generated per-creative availability; blank duration, zeroes, weighting and unrelated formulas preserved; native spreadsheet/export review pending.
- Benefit to verify: Use the same duration eligibility for individual and pooled calculations.
- Status: implemented pending verification (not verified).

### QI124 — The XLSX writer coerces numeric-looking text into numbers

- Findings: QI124; severity high; kind defect; workstream B5.
- Original locations (pin `1342bb4`): Backend/creative_intel/ooxml.py:412-412.
- Files: Backend/creative_intel/ooxml.py.
- Change (Mac `06d163d`): Writer no longer coerces strings via str_or_num; strings stay text cells. Tests: tests/test_ooxml_quality.py text-identity round-trips.
- Benefit to verify: Preserve string identity and require explicit numeric cell intent.
- Status: implemented pending verification (not verified).

### QI126 — Worksheet selection follows ZIP filenames instead of workbook tab order

- Findings: QI126; severity high; kind defect; workstream B5.
- Original locations (pin `1342bb4`): Backend/creative_intel/ooxml.py:540-547.
- Files: Backend/creative_intel/ooxml.py.
- Change (Mac `06d163d`): Parser resolves worksheets via workbook catalogue + relationships in tab order. Tests: 12-sheet, reordered-catalogue, missing-rels cases.
- Benefit to verify: Use the workbook catalogue and relationship order consistently.
- Status: implemented pending verification (not verified).

### QI142 — Workbook label formatting alters creative identifiers and CTA text

- Findings: QI142; severity high; kind defect; workstream B5.
- Original locations (pin `1342bb4`): Backend/creative_intel/benchmarks.py:1839-1839; Backend/creative_intel/benchmarks.py:1841-1841.
- Files: Backend/creative_intel/benchmarks.py.
- Change (import `1ba11ab`, historical batch P12_exact_workbook_labels `dc4806e`): Creative identifiers and CTA values bypass slug humanization; exact isolated formatting tested; full workbook integration pending.
- Benefit to verify: Preserve exact identifiers and text while humanizing only categorical codes.
- Status: implemented pending verification (not verified).

### QI145 — Known currency metadata hides money rows with unknown currency

- Findings: QI145; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/benchmarks.py:46-46; Backend/creative_intel/benchmarks.py:48-48.
- Files: Backend/creative_intel/benchmarks.py.
- Change (import `1ba11ab`, historical batch P03_partial `b5f73b7`): QI145 backend classification implemented; QI057 ratio portion implemented, raw-total/period-comparison portion remains open.
- Benefit to verify: Expose uncertainty and prevent unsupported currency-bearing comparisons.
- Status: implemented pending verification (not verified).

### QI323 — Report test plans match rule IDs without retaining the creative

- Findings: QI323; severity high; kind defect; workstream B1.
- Original locations (pin `1342bb4`): Backend/creative_intel/analyst_chat.py:528-534.
- Files: Backend/creative_intel/analyst_chat.py.
- Change (Mac `4c3344a`, note in `8305af3`): Index findings by (finding_id, creative_ids); exactly one match required; missing/ambiguous plans omitted with a reader-visible Tests note (EN/PL, no backfill); owner passed as control. Claim covers build_analyst_report only. Tests: tests/test_analyst_report_quality.py (8 cases).
- Benefit to verify: Retain or uniquely index the exact recommendation source finding.
- Status: implemented pending verification (not verified).

## Newly completed in this increment (verify these first)

Checkpoint 032 completions below were already on main. This push does
not edit them. Verify QI043 and QI045 above first.

- QI060 (0772b15): Campaigns spend bench gated on comparable currency;
  rail ROAS pooled from reporting components. Prior Dashboard/Analyst
  baselines already on main. Tests: CampaignsPage suite + full UI.
- QI269/QI270 (2f3e98b): annotation associations asserted both orders and
  N-way in tests/test_why_associations_quality.py atop ordering fixes.
- Advanced but still partial: QI016 daily canonical (432ab38 backend +
  0772b15 Compare), QI150 benchmark_filtered + QA money gate (432ab38),
  QI176 coverage label + QA currency (432ab38). See updated remainders.

## Partly done — do not ship these claims as complete (6; QI060/QI269 entries below are completion records)

### QI016 — UI ROAS recomputation loses the revenue-reporting population (PARTIAL)

- Findings: QI016, QI095; severity high; kind defect. Files: Backend/creative_intel/benchmarks.py; apps/creative-intelligence-ui/src/pages/AnalystPage.tsx; apps/creative-intelligence-ui/src/pages/CampaignsPage.tsx; apps/creative-intelligence-ui/src/pages/ComparePage.tsx; apps/creative-intelligence-ui/src/pages/DashboardPage.tsx; apps/creative-intelligence-ui/src/pages/OverviewPage.tsx.
- Original locations: apps/creative-intelligence-ui/src/pages/DashboardPage.tsx:158-158; apps/creative-intelligence-ui/src/pages/ComparePage.tsx:556-556; Backend/creative_intel/benchmarks.py:215-222; apps/creative-intelligence-ui/src/pages/CampaignsPage.tsx:431-431. Benefit: Make charts and baselines agree with the canonical reporting-population KPI.
- Remaining: Dashboard, Analyst platform baseline, Campaigns pooling and Compare daily canonical KPIs done (432ab38/0772b15). Remaining: Analyst length-band ROAS wiring sits on deferred AnalystPage lines (blocked, not bypassed), legacy Overview (unrouted; retain/retire decision), canonical payload/coverage presentation.
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI017 — Money displays assume USD despite native-currency backend values (PARTIAL)

- Findings: QI017; severity high; kind defect. Files: Backend/creative_intel/benchmarks.py; Backend/creative_intel/period_compare.py; Backend/creative_intel/qa.py; apps/creative-intelligence-ui/src/components/product.tsx; apps/creative-intelligence-ui/src/i18n/locales/en.ts; apps/creative-intelligence-ui/src/i18n/locales/es.ts; apps/creative-intelligence-ui/src/i18n/locales/pl.ts; apps/creative-intelligence-ui/src/pages/DashboardPage.tsx; apps/creative-intelligence-ui/src/pages/OverviewPage.tsx.
- Original locations: apps/creative-intelligence-ui/src/components/product.tsx:40-40; apps/creative-intelligence-ui/src/components/product.tsx:45-46; apps/creative-intelligence-ui/src/components/product.tsx:51-51; apps/creative-intelligence-ui/src/components/product.tsx:54-54. Benefit: Show the actual denomination and explicitly distinguish mixed or unknown currencies.
- Remaining: Dashboard/period slices done. Remaining: USD-hardcoded formatters in product.tsx, ComparePage, CampaignsPage, AskPage, WorkbookPage; locale spend-band copy (guard-blocked ranges nearby); benchmarks/QA prose in mixed owners; Overview; legacy unknown-unit labels beyond implemented slices.
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI028 — Zero-spend benchmark weights manufacture a zero weighted mean (PARTIAL)

- Findings: QI028; severity medium; kind defect. Files: Backend/creative_intel/benchmarks.py.
- Original locations: Backend/creative_intel/benchmarks.py:480-480; Backend/creative_intel/benchmarks.py:484-484. Benefit: Show unavailable weighted means while preserving valid unweighted percentiles.
- Remaining: Pure describe_bands fixed; zero-spend _weight instance fixed in 8305af3 (summarize conv_rate_weighted now unavailable). Remaining: mixed backend propagation of null weighted mean to consumers (withheld owners).
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI057 — Aggregate totals and common KPIs turn unreported fields into measured zeroes (PARTIAL)

- Findings: QI057; severity high; kind defect. Files: Backend/creative_intel/benchmarks.py; Backend/creative_intel/period_compare.py.
- Original locations: Backend/creative_intel/benchmarks.py:127-132; Backend/creative_intel/benchmarks.py:405-409; Backend/creative_intel/period_compare.py:65-70. Benefit: Share availability-aware totals and matched-population ratios across consumers.
- Remaining: Ratios + period raw totals done. Remaining: benchmarks raw totals retain legacy numeric API by design in summarize/kpis_for_rows; frontend nullable raw-total presentation in deferred-heavy pages.
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI060 — Dashboard and Campaigns baselines pool unlike currency amounts (COMPLETED 032)

- Findings: QI060, QI101; severity high; kind defect. Files: apps/creative-intelligence-ui/src/pages/AnalystPage.tsx; apps/creative-intelligence-ui/src/pages/CampaignsPage.tsx; apps/creative-intelligence-ui/src/pages/DashboardPage.tsx.
- Original locations: apps/creative-intelligence-ui/src/pages/DashboardPage.tsx:152-152; apps/creative-intelligence-ui/src/pages/DashboardPage.tsx:159-160; apps/creative-intelligence-ui/src/pages/CampaignsPage.tsx:431-431; apps/creative-intelligence-ui/src/pages/CampaignsPage.tsx:433-435. Benefit: Use canonical or single-currency baselines and omit incomparable results.
- Remaining: none. Campaigns platform spend bench now gated on comparable currency and rail ROAS pooled from reporting components (0772b15); full UI suite passes.
- Status: implemented pending verification (not verified).

### QI150 — Cost comparisons and recommendation pools mix native currency units (PARTIAL)

- Findings: QI150; severity high; kind defect. Files: Backend/ci_backend/actions.py; Backend/creative_intel/benchmarks.py; Backend/creative_intel/qa.py.
- Original locations: Backend/creative_intel/benchmarks.py:819-820; Backend/creative_intel/benchmarks.py:958-958; Backend/creative_intel/benchmarks.py:977-977; Backend/creative_intel/benchmarks.py:1218-1218. Benefit: Apply one comparable-currency policy to unit-bearing rankings and recommendations.
- Remaining: Creative/campaign/dashboard, benchmark_filtered bands and QA _group_metric money gate done (432ab38). Remaining: benchmarks _report_extras/campaign_recommendations/build_report (mixed), QA _fact_pack (mixed), markets/peer pools. Legacy wholly-unspecified arithmetic preserved by 58251b1.
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI176 — QA ROAS rankings ignore revenue-reporting coverage (PARTIAL)

- Findings: QI176; severity high; kind defect. Files: Backend/creative_intel/qa.py; tests/test_ask_llm.py.
- Original locations: Backend/creative_intel/qa.py:596-596; Backend/creative_intel/qa.py:601-602; tests/test_ask_llm.py:184-186. Benefit: Use matched ROAS with explicit reported fixtures and unavailable handling.
- Remaining: Winner selection, single-winner coverage label and QA money-currency gate done (7bce053/432ab38). Remaining: tied-winner coverage labels and _fact_pack currency in mixed owner.
- Status: partial. Verify done slices; report remainder as missing, not as a new defect unless worsened.

### QI269 — Comparison explanations reverse the paired values when the second creative leads (COMPLETED 032)

- Findings: QI269, QI270; severity medium; kind defect. Files: Backend/ci_backend/actions.py; tests/test_acceptance_10.py; tests/test_cohorts_compare.py.
- Original locations: Backend/ci_backend/actions.py:143-145; tests/test_cohorts_compare.py:466-468; tests/test_cohorts_compare.py:531-534; tests/test_acceptance_10.py:1030-1031. Benefit: Order values with their owners or label each value explicitly.
- Remaining: none. QI270 annotation associations asserted both orders and N-way in tests/test_why_associations_quality.py (2f3e98b); metric associations already covered.
- Status: implemented pending verification (not verified).

## Integration triage you must judge (commit `58251b1`)

Full-suite integration exposed 11 failures in currency-less legacy
fixtures. Resolution kept known-currency protections and restored
legacy arithmetic only for explicitly wholly-unspecified producer
scopes (`currencies=[]`): `creative_comparison.cost_comparison_reason`,
`period_metrics.manual_period_deltas`. Absent metadata and
known-plus-unknown mixes stay unavailable. One existing expectation
was corrected for QI019 (undefined prior CPA is `none`, measured
current retained) in `tests/test_period_compare.py`. Direct fixtures
now declare currency explicitly. Falsify this boundary: try known+
unknown, mixed flags, absent keys, and legacy DB rows with blank
currency. Denomination is still never invented for labels.

## Mac re-audit residuals tracked, not fixed in this push

Three independent read-only Mac re-audits (backend, UI, integrity) returned
ship-after-fixes; their medium defects were fixed in `8305af3` (QI046
multi-row reach pricing, zero-weight manufactured mean, plus low reason/
strictness fixes). These lows remain tracked follow-ups — confirm they are
still true, do not re-report them as undisclosed:

- Dashboard hook chart converts an unavailable CTR baseline to zero though
  the shared chart supports null (reachable mainly with legacy metadata).
- Singleton chart accessibility text interpolates the raw number, so es/pl
  users hear a decimal point where the axis shows a comma.
- QI126 requires catalogue relationships on every sheet; workbooks without
  them now get a clear ValueError instead of filename fallback.
- QI323 int-vs-str creative_ids are normalized by str() but untested as
  mixed types; deferred answer_turn plan call sites are outside the claim.
  Polish omission note and divergent-owner control are now tested (c0eaf8a).

## Evidence (Mac, current — check plausibility, do not re-run)

- Restoration: patch SHA256 `0015f6ab…`, tree `b3d4d169…` exact, 74/74 file hashes.
- Scoped (adapted copies; sealed runners untouched): Python 338 passed
  (15 checkpoint-030 quality files), UI 316 passed, TypeScript 45 entries pass.
  Historical cloud checkpoint-030 counts were Python 332, UI 316, TS 45.
- Full Python baseline (pristine): 913 passed, 5 failed, 1 skipped (919).
  Full Python at code head `b690c69`: 1,319 passed, 4 failed, 1 skipped,
  193 subtests, 352.08s. The new module is
  `tests/test_checkpoint_036_highs.py` (30 passed on its own).
  The 338-test scoped subset above also passes inside this full suite;
  newer QI323/QI176/XLSX quality tests are full-suite only and included.
  Failures are only pre-existing `0012` vs `0013`: three
  `tests/test_ci_migrations.py` tests + `test_deploy_migration_command_from_repo_root`.
  (`test_no_licensing_concepts` passes in the import tree layout; it is
  environmental (`.venv` walker), not fixed by this push. React-dist tests
  pass after the UI build; ffmpeg-host test skips.)
  Command, from the implementation worktree, using the main checkout
  venv: `python -m pytest tests/ -q --tb=line`.
  The 4 failures are only the pre-existing `0012` vs `0013` mismatch
  (`tests/test_ci_migrations.py` lines 37, 86, and 106, and
  `tests/test_deploy.py` line 134).
  The skip is `tests/test_acceptance_10.py` (needs a no-ffmpeg host).
  193 subtests passed.
- This push changes no UI file. `tsc`, `vitest`, and `vite build` were
  not re-run. The previous local build assets remain
  `index-GrNu5x1A.js` (968,779 bytes) and `index-C5G5cbmt.css`
  (72,151 bytes). The browser was not used.
- `Source/self_check.py` at this code head: 97/97.
  `ruff check` on `review_bind.py`, `ingest.py`, `qa.py`,
  `retention.py`, `schema.py`, `worker.py`, `test_mvp.py`, and
  `test_checkpoint_036_highs.py` was clean. `product.py` still has
  the same 20 findings as at `92edef8`; none are in the edited
  rebind window. No tracked CI config exists; exact-commit CI is
  unavailable, not passed. No live browser, live provider, or native
  Excel check was run. Deployment of this push was not verified when
  this file was written.

## Still open (272 untouched groups — summary)

Untouched alone: 0 high, 177 medium, 95 low. With the 6 partials
(5 high, 1 medium): 5 high, 178 medium, 95 low remaining. Remaining
is 278 (272 untouched + 6 partial). Remaining by kind including
partials: 149 defects, 33 conditional risks, 45 test gaps,
51 improvements. Conditional risks are hypotheses to validate, not bugs to
blindly fix. The ten highs in this push are pending verification, not
untouched. The high partials that remain are QI016, QI017, QI057,
QI150, and QI176. QI028 remains the medium partial.
B9 inactive-prototype groups (28) need retain/retire decisions; B10 fallback
(14) stays separate. Full per-group status is in the appendix. The complete
finding evidence lives in the preserved handoff register; this file does
not replace it. QI044 stays
untouched: it is a conditional risk on stored multi-value filters, and the
current scope model is one string per axis. Next fresh triage, not done
here: QI047. Do not retry deferred owners wholesale.

## Independent recheck steps

1. Verify target/diff above; confirm `Audit.md`-only commits after code head.
2. For each implemented group, trace producer → helper → consumer and read
   its regression tests; try the finding's triggering conditions on paper.
3. For partials, confirm each remaining consumer still shows old behavior.
4. Spot-check untouched highs still exist at cited symbols (follow symbols).
5. Reconcile counts: appendix rows = 326; finding IDs across rows = 335.

## Appendix — all 326 groups at this push

| Group | Findings | Sev | Kind | Status | Title |
|---|---|---|---|---|---|
| QI-001 | QI-001 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Video-only analysis cannot complete the normal review workflow |
| QI-002 | QI-002 | medium | defect | NOT_IMPLEMENTED | Repeated tooltip resize adjustments undo the previous collision correction |
| QI-003 | QI-003 | medium | defect | NOT_IMPLEMENTED | Tooltip positioning keeps the old responsive mode after crossing the breakpoint |
| QI-004 | QI-004 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Comma-delimited comparison selections cannot preserve campaign names containing commas |
| QI-005 | QI-005 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | A failed KPI refresh leaves prior-scope values displayed as current |
| QI-006 | QI-006 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Daily-series request failures are presented as an empty dataset |
| QI-007 | QI-007 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Top Performer benchmark uses the worst CPA/CPC value |
| QI-008 | QI-008 | medium | defect | NOT_IMPLEMENTED | Translated metric labels prevent shared KPI comparisons from resolving |
| QI-009 | QI-009 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Several analytics and preview panels retain loading visuals after failed requests |
| QI-010 | QI-010 | medium | defect | NOT_IMPLEMENTED | InfoTip immediately closes on the first focus-then-click interaction |
| QI-011 | QI-011,QI303 | low | improvement | NOT_IMPLEMENTED | OverflowMenu documentation promises a body portal that is not rendered |
| QI-012 | QI-012 | medium | defect | NOT_IMPLEMENTED | Retention callout can label one sample while pointing at another |
| QI013 | QI013 | medium | defect | NOT_IMPLEMENTED | Creative retention comparisons discard elapsed-time coordinates |
| QI014 | QI014 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Creative deep links run CTR while the rank selector displays ROAS |
| QI015 | QI015 | low | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Fractional chart ticks are rounded into duplicate integer labels |
| QI016 | QI016,QI095 | high | defect | PARTIALLY_IMPLEMENTED | UI ROAS recomputation loses the revenue-reporting population |
| QI017 | QI017 | high | defect | PARTIALLY_IMPLEMENTED | Money displays assume USD despite native-currency backend values |
| QI018 | QI018 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Manual period comparison subtracts amounts in different currencies |
| QI019 | QI019 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Missing prior measurements are described as measured zero |
| QI020 | QI020 | low | defect | NOT_IMPLEMENTED | Thumbnail failure persists after the creative changes |
| QI021 | QI021 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Dashboard downsampling creates unequal totals under single-day labels |
| QI022 | QI022 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Benchmark mini charts turn unavailable metrics into zero |
| QI023 | QI023 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Benchmark group changes can preselect keys from the previous response |
| QI024 | QI024 | medium | test_gap | NOT_IMPLEMENTED | Benchmark comparison test can pass with the comparison panel empty |
| QI025 | QI025 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Average watch time drops measured-zero rows from its denominator |
| QI026 | QI026 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Watch-time average fallback is unreachable when totals are absent |
| QI027 | QI027 | medium | improvement | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Pooled ratio repeatedly scans row lists quadratically |
| QI028 | QI028 | medium | defect | PARTIALLY_IMPLEMENTED | Zero-spend benchmark weights manufacture a zero weighted mean |
| QI030 | QI030 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Period comparison results survive changes to the active filter scope |
| QI031 | QI031 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Isolated trend points produce no visible SVG stroke |
| QI032 | QI032 | medium | defect | NOT_IMPLEMENTED | Charts expose only generic labels instead of their plotted data |
| QI033 | QI033 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Frequency fallback combines all impressions with one partial reach row |
| QI034 | QI034 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Engagement pools numerator and denominator from different populations |
| QI035 | QI035 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Header aliases choose conflicting columns in unordered set order |
| QI036 | QI036 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Missing revenue markers can be flagged as reported zero |
| QI037 | QI037 | high | conditional_risk | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Import facts and provenance counts commit in separate transactions |
| QI038 | QI038 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Synthetic retention divides reported quartiles by unreported exposure |
| QI039 | QI039 | medium | defect | NOT_IMPLEMENTED | Timed element labels ignore the requested moment for CTA and voiceover |
| QI040 | QI040 | medium | defect | NOT_IMPLEMENTED | Percentage formatting guesses units from magnitude |
| QI041 | QI041 | medium | defect | NOT_IMPLEMENTED | Suggested comparison tests skip genuine zero performance |
| QI042 | QI042 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Benchmark CPM bypasses the canonical mixed-currency result |
| QI043 | QI043 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Failed comparison options become an impossible selection instruction |
| QI044 | QI044 | medium | conditional_risk | NOT_IMPLEMENTED | Saved views restore only the first value of multi-value filters |
| QI045 | QI045 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Filter panels hide metadata failures as empty option lists |
| QI046 | QI046 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Cost per thousand reached turns missing spend into measured zero |
| QI047 | QI047 | medium | defect | NOT_IMPLEMENTED | Comparison chart failures are substituted with empty series |
| QI048 | QI048 | medium | defect | NOT_IMPLEMENTED | Saved benchmark fetch failures appear as an empty saved list |
| QI049 | QI049 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Format recommendations do not reverse when the other group wins |
| QI050 | QI050 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Positive diagnostic findings turn a layer into a concern |
| QI051 | QI051 | medium | defect | NOT_IMPLEMENTED | Format-comparison confidence counts creatives without usable metric data |
| QI052 | QI052 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Daily scale diagnostics can compare money amounts in different currencies |
| QI053 | QI053 | medium | conditional_risk | NOT_IMPLEMENTED | Unexpected diagnostic-rule failures disappear from analysis results |
| QI054 | QI054 | low | improvement | NOT_IMPLEMENTED | Classification metadata calls median margins tertiles |
| QI055 | QI055 | medium | defect | NOT_IMPLEMENTED | Brand-recall findings can omit the metric that triggered them |
| QI056 | QI056 | medium | defect | NOT_IMPLEMENTED | Saving a benchmark depends on an unused extra request |
| QI057 | QI057 | high | defect | PARTIALLY_IMPLEMENTED | Aggregate totals and common KPIs turn unreported fields into measured zeroes |
| QI058 | QI058 | low | improvement | NOT_IMPLEMENTED | Date-range docstring promises filtered extent but uses dataset extent |
| QI059 | QI059 | medium | defect | NOT_IMPLEMENTED | Saved benchmark confirmation is lost if the subsequent list refresh fails |
| QI060 | QI060,QI101 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Dashboard and Campaigns baselines pool unlike currency amounts |
| QI061 | QI061 | low | defect | NOT_IMPLEMENTED | An old retention error survives a switch to an empty scope |
| QI063 | QI063 | medium | defect | NOT_IMPLEMENTED | Format chart converts a zero denominator into measured CTR zero |
| QI064 | QI064 | medium | defect | NOT_IMPLEMENTED | Insight navigation reloads the app and loses active filters |
| QI065 | QI065 | medium | defect | NOT_IMPLEMENTED | Reopening sample data drops the saved campaign-preference return state |
| QI066 | QI066 | medium | defect | NOT_IMPLEMENTED | Closed mobile navigation remains keyboard-focusable off screen |
| QI067 | QI067 | medium | defect | NOT_IMPLEMENTED | Several dark-theme controls use near-matching text and background colours |
| QI068 | QI068 | medium | defect | NOT_IMPLEMENTED | Search request failures are cached as empty successful indexes |
| QI069 | QI069 | medium | improvement | NOT_IMPLEMENTED | Typing before search initialization finishes starts repeated full-index requests |
| QI070 | QI070 | medium | defect | NOT_IMPLEMENTED | Search keyboard selection has no active-option accessibility relationship |
| QI071 | QI071 | medium | defect | NOT_IMPLEMENTED | Search arrow keys can select a hidden result or the wrong initial option |
| QI072 | QI072 | low | conditional_risk | NOT_IMPLEMENTED | Later subtitle rule overrides the stated tablet-width exception |
| QI073 | QI073 | medium | conditional_risk | NOT_IMPLEMENTED | Search result keys use display labels that need not be unique |
| QI074 | QI074 | medium | test_gap | NOT_IMPLEMENTED | Search navigation test checks dismissal but never the destination |
| QI075 | QI075 | low | improvement | NOT_IMPLEMENTED | A duplicate active-button rule silently replaces the accent token |
| QI076 | QI076 | low | defect | NOT_IMPLEMENTED | Server preference-save failures are described as browser-storage failures |
| QI077 | QI077 | low | defect | NOT_IMPLEMENTED | Several Settings option labels remain English after the interface language changes |
| QI078 | QI078 | low | improvement | NOT_IMPLEMENTED | Locale-provider comments still describe a staged Save workflow |
| QI079 | QI079 | medium | defect | NOT_IMPLEMENTED | Report calendar dates are shifted by the user timezone in their display label |
| QI080 | QI080 | low | defect | NOT_IMPLEMENTED | Valid plural fallbacks create spurious missing-translation diagnostics |
| QI081 | QI081 | low | defect | NOT_IMPLEMENTED | Several Polish count messages reuse incorrect noun forms |
| QI082 | QI082 | medium | defect | NOT_IMPLEMENTED | Reloading a regenerating report can leave its history row permanently busy |
| QI083 | QI083 | medium | defect | NOT_IMPLEMENTED | Report time filters parse localized display strings as timestamps |
| QI084 | QI084 | medium | defect | NOT_IMPLEMENTED | Regenerating a synthetic demo row never installs its downloadable result |
| QI085 | QI085 | medium | conditional_risk | NOT_IMPLEMENTED | A report that finishes after unmount can create an unreleased object URL |
| QI086 | QI086 | medium | defect | NOT_IMPLEMENTED | Applying a template with no selected KPIs retains the previous selection |
| QI087 | QI087 | low | defect | NOT_IMPLEMENTED | Latest Generated Files follows source concatenation rather than creation time |
| QI088 | QI088 | medium | defect | NOT_IMPLEMENTED | Report-template list failures are silently presented as an empty or stale list |
| QI089 | QI089 | low | defect | NOT_IMPLEMENTED | Report-template server errors are labeled as browser-save failures |
| QI090 | QI090 | medium | defect | NOT_IMPLEMENTED | Closing the report date popup can discard keyboard focus |
| QI091 | QI091 | medium | conditional_risk | NOT_IMPLEMENTED | An older template-list response can overwrite a newer list |
| QI092 | QI092 | medium | defect | NOT_IMPLEMENTED | Default-accent report focus and selected-state cues have insufficient contrast |
| QI093 | QI093 | medium | defect | NOT_IMPLEMENTED | Video-length recommendations describe CTR leadership as attention retention |
| QI094 | QI094 | medium | defect | NOT_IMPLEMENTED | Length chart draws unavailable band metrics as measured zeroes |
| QI096 | QI096 | medium | defect | NOT_IMPLEMENTED | Analyst chart request failures can remain permanent loading skeletons |
| QI097 | QI097 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Selecting Custom Range sends NaN into the shared date helper |
| QI098 | QI098 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Top Creatives does not implement its advertised ROAS-then-CTR ordering |
| QI099 | QI099 | medium | test_gap | NOT_IMPLEMENTED | Page scope-request tests do not verify nonempty selected filters |
| QI100 | QI100 | medium | defect | NOT_IMPLEMENTED | The length chart exposes no numeric ROAS scale or accessible ROAS values |
| QI102 | QI102 | medium | conditional_risk | NOT_IMPLEMENTED | Overlapping cohort requests can replace newer results with older responses |
| QI103 | QI103 | medium | defect | NOT_IMPLEMENTED | Cohort creation loses its success state when the follow-up refresh fails |
| QI104 | QI104 | low | improvement | NOT_IMPLEMENTED | Legacy layout/filter comments do not identify their current role |
| QI105 | QI105 | low | defect | NOT_IMPLEMENTED | Campaigns leaves KPI numbers and unavailable messages in the default locale |
| QI106 | QI106 | medium | defect | NOT_IMPLEMENTED | Campaign count displays zero while its independent request is unknown |
| QI107 | QI107 | medium | defect | NOT_IMPLEMENTED | Campaigns KPI selector cannot represent several shared filter values |
| QI108 | QI108 | low | defect | NOT_IMPLEMENTED | A retried campaign detail request continues showing its previous error |
| QI109 | QI109 | low | improvement | NOT_IMPLEMENTED | The Campaigns legacy focus request writes only discarded state |
| QI110 | QI110 | medium | defect | NOT_IMPLEMENTED | Switching creative details temporarily shows the previous retention curve |
| QI111 | QI111 | medium | defect | NOT_IMPLEMENTED | Retention request failures are rendered as successful no-curve results |
| QI112 | QI112 | medium | test_gap | NOT_IMPLEMENTED | Several Creative-page tests wait for a heading that exists before data loads |
| QI113 | QI113 | medium | test_gap | NOT_IMPLEMENTED | The Creative length-filter test claims KPI coverage but only checks its banner |
| QI114 | QI114 | medium | defect | NOT_IMPLEMENTED | The Workbook marks Executive Summary selected while initializing a different configuration |
| QI115 | QI115 | medium | defect | NOT_IMPLEMENTED | Workbook fullscreen preview lacks modal keyboard focus management |
| QI116 | QI116 | medium | defect | NOT_IMPLEMENTED | Workbook preview and module copy overstate the blank file being downloaded |
| QI117 | QI117 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | The weak-hold worksheet rule compares 3-second hook against the 2-second benchmark |
| QI118 | QI118 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Pooled workbook hold includes durations rejected by the per-creative formula |
| QI119 | QI119 | medium | defect | NOT_IMPLEMENTED | Blank or wholly unavailable workbook metrics have unguarded mean and median formulas |
| QI120 | QI120 | medium | defect | NOT_IMPLEMENTED | The Input sheet silently drops its single-currency instruction |
| QI121 | QI121 | medium | defect | NOT_IMPLEMENTED | The weak-hold hypothesis guard misses the short-video unavailable marker |
| QI122 | QI122 | low | improvement | NOT_IMPLEMENTED | The workbook instructions print a doubled percent sign |
| QI123 | QI123 | low | improvement | NOT_IMPLEMENTED | The Workbook date comment names the wrong timezone direction |
| QI124 | QI124 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | The XLSX writer coerces numeric-looking text into numbers |
| QI125 | QI125 | medium | defect | NOT_IMPLEMENTED | Spreadsheet text and sheet names retain XML escape sequences |
| QI126 | QI126 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Worksheet selection follows ZIP filenames instead of workbook tab order |
| QI127 | QI127 | low | defect | NOT_IMPLEMENTED | Workbook names are silently truncated in the downloaded file |
| QI128 | QI128 | low | improvement | NOT_IMPLEMENTED | The workbook test header overstates formula agreement coverage |
| QI129 | QI129 | low | improvement | NOT_IMPLEMENTED | Workbook comments claim registry-driven formula generation that is manually mirrored |
| QI130 | QI130 | medium | defect | NOT_IMPLEMENTED | PPTX theme colors are emitted in the wrong schema order |
| QI131 | QI131 | medium | defect | NOT_IMPLEMENTED | PPTX theme omits its required font scheme |
| QI132 | QI132 | medium | defect | NOT_IMPLEMENTED | PPTX layout uses a nonexistent layout enum value |
| QI133 | QI133 | medium | defect | NOT_IMPLEMENTED | PPTX presentation omits required notes-page dimensions |
| QI134 | QI134 | low | improvement | NOT_IMPLEMENTED | Spreadsheet exports carry a fictitious presentation slide count |
| QI135 | QI135 | low | improvement | NOT_IMPLEMENTED | Shared-string metadata counts unique entries as total occurrences |
| QI136 | QI136 | medium | defect | NOT_IMPLEMENTED | Exported headings use a low-contrast teal and white pairing |
| QI137 | QI137 | medium | defect | NOT_IMPLEMENTED | A worksheet with no cells in row one raises an unhandled KeyError |
| QI138 | QI138 | medium | defect | NOT_IMPLEMENTED | Cached formula values are contaminated when the formula has attributes |
| QI139 | QI139 | medium | defect | NOT_IMPLEMENTED | Unavailable KPIs displace the actual measured trailer |
| QI140 | QI140 | medium | defect | NOT_IMPLEMENTED | CTA recommendations report the upper middle value as the median |
| QI141 | QI141 | medium | defect | NOT_IMPLEMENTED | CSV cells containing a standalone carriage return are left unquoted |
| QI142 | QI142 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Workbook label formatting alters creative identifiers and CTA text |
| QI143 | QI143 | low | defect | NOT_IMPLEMENTED | The no-computable-ranking state claims there is one ranked creative |
| QI144 | QI144 | low | improvement | NOT_IMPLEMENTED | The ROAS helper docstring overstates zero coverage for empty populations |
| QI145 | QI145 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Known currency metadata hides money rows with unknown currency |
| QI146 | QI146 | medium | defect | NOT_IMPLEMENTED | Resolving campaign-level filters loses an explicit empty selection |
| QI147 | QI147 | medium | defect | NOT_IMPLEMENTED | Campaign-axis resolution changes matching to case-sensitive |
| QI148 | QI148 | medium | defect | NOT_IMPLEMENTED | Sample-only scope descriptions say All Data |
| QI149 | QI149 | low | conditional_risk | NOT_IMPLEMENTED | Spend-bound validation accepts non-finite numeric values |
| QI150 | QI150 | high | defect | PARTIALLY_IMPLEMENTED | Cost comparisons and recommendation pools mix native currency units |
| QI151 | QI151 | medium | defect | NOT_IMPLEMENTED | PowerPoint reports omit their analytical and benchmark scope |
| QI152 | QI152 | low | improvement | NOT_IMPLEMENTED | The earliest-span helper is duplicated inside report generation |
| QI153 | QI153 | medium | defect | NOT_IMPLEMENTED | The prototype hook answer crashes on an empty verified population |
| QI154 | QI154 | medium | defect | NOT_IMPLEMENTED | Prototype length answers choose an empty duration group as the winner |
| QI155 | QI155 | medium | defect | NOT_IMPLEMENTED | Several prototype recommendations assert attributes they never measure |
| QI156 | QI156 | low | defect | NOT_IMPLEMENTED | Prototype self-check artifacts are labelled with a cohort they did not filter |
| QI157 | QI157 | medium | defect | NOT_IMPLEMENTED | Prototype date validation accepts impossible calendar dates |
| QI158 | QI158 | low | defect | NOT_IMPLEMENTED | Prototype quarantine positions shift after blank CSV records |
| QI159 | QI159 | medium | defect | NOT_IMPLEMENTED | Prototype unavailable ratios are represented as measured zeroes |
| QI160 | QI160 | medium | defect | NOT_IMPLEMENTED | The prototype accepts missing duration that breaks rendering and length grouping |
| QI161 | QI161 | medium | defect | NOT_IMPLEMENTED | Prototype dashboard badges ignore insufficient benchmark evidence |
| QI162 | QI162 | medium | defect | NOT_IMPLEMENTED | Generic format questions are forced into the TikTok-only branch |
| QI163 | QI163 | medium | defect | NOT_IMPLEMENTED | The interchange schema still labels plays as VTR |
| QI164 | QI164 | low | improvement | NOT_IMPLEMENTED | The schema overstates cross-engine weighting agreement |
| QI165 | QI165 | low | defect | NOT_IMPLEMENTED | Dark prototype benchmark badges have insufficient text contrast |
| QI166 | QI166 | low | defect | NOT_IMPLEMENTED | Prototype CSV exports omit their promised lineage information |
| QI167 | QI167 | medium | defect | NOT_IMPLEMENTED | Prototype creative joins combine metrics under one arbitrary cohort tag |
| QI168 | QI168 | low | defect | NOT_IMPLEMENTED | Prototype timing recommendations call an equal CPA a late-appearance win |
| QI169 | QI169 | medium | defect | NOT_IMPLEMENTED | Unknown project identifiers count toward the prototype evidence minimum |
| QI170 | QI170 | low | conditional_risk | NOT_IMPLEMENTED | The prototype one-pager reverses non-cost benchmark verdicts |
| QI171 | QI171 | low | improvement | NOT_IMPLEMENTED | The prototype self-check leaves temporary artifacts and shares fixture filenames |
| QI172 | QI172 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | QA compares completion rate with play rate when timing groups have different measures |
| QI173 | QI173,QI259 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | QA renders unavailable CTR and format CPA as measured zeroes |
| QI174 | QI174 | medium | defect | NOT_IMPLEMENTED | QA structure summaries count ad rows as creatives |
| QI175 | QI175 | medium | defect | NOT_IMPLEMENTED | Backend QA substitutes TikTok for other format questions |
| QI176 | QI176 | high | defect | PARTIALLY_IMPLEMENTED | QA ROAS rankings ignore revenue-reporting coverage |
| QI177 | QI177 | medium | defect | NOT_IMPLEMENTED | A named platform overrides the creative or campaign answer level |
| QI178 | QI178 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | QA top-versus-bottom groups ignore the requested ranking metric |
| QI179 | QI179 | medium | defect | NOT_IMPLEMENTED | The legacy canonical normalizer discards native currency values |
| QI180 | QI180 | medium | defect | NOT_IMPLEMENTED | QA treats unannotated creatives as confirmed to have no CTA |
| QI181 | QI181 | medium | improvement | NOT_IMPLEMENTED | Every QA fact-pack topic incurs per-creative database round trips |
| QI182 | QI182 | medium | defect | NOT_IMPLEMENTED | Prototype video-view aliases collapse different measures into one numerator |
| QI183 | QI183 | medium | defect | NOT_IMPLEMENTED | Prototype TikTok ad-group aliases overwrite creative identifiers |
| QI184 | QI184 | medium | defect | NOT_IMPLEMENTED | Segment-level brand matching accepts substrings inside unrelated words |
| QI185 | QI185 | medium | conditional_risk | NOT_IMPLEMENTED | All-false observations leave conflicting model appearance spans intact |
| QI186 | QI186 | medium | defect | NOT_IMPLEMENTED | A percentage sign alone is classified as a discount |
| QI187 | QI187 | medium | conditional_risk | NOT_IMPLEMENTED | Shared diacritics are treated as a unique Slovenian language signal |
| QI188 | QI188 | low | test_gap | NOT_IMPLEMENTED | The pooled-CTR test cannot distinguish pooling from averaging row rates |
| QI189 | QI189,QI280 | medium | defect | NOT_IMPLEMENTED | Short-clip sampling includes a timestamp at the clip duration |
| QI190 | QI190 | low | conditional_risk | NOT_IMPLEMENTED | Small frame caps are exceeded by the retained dense opening |
| QI191 | QI191 | medium | conditional_risk | NOT_IMPLEMENTED | An invalid cached JPEG is skipped on every later preparation |
| QI192 | QI192 | medium | conditional_risk | NOT_IMPLEMENTED | Invalid-WAV cleanup can remove a peer’s newly published cache |
| QI193 | QI193 | medium | defect | NOT_IMPLEMENTED | Creative reports omit metric units and print unavailable values as None |
| QI194 | QI194 | medium | test_gap | NOT_IMPLEMENTED | The video-only report assertion permits fabricated metrics beside an unavailable notice |
| QI195 | QI195 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Ask answers remain paired with newly filtered KPI context |
| QI196 | QI196 | medium | defect | NOT_IMPLEMENTED | Ask turns a recent-conversation request failure into no recent chats |
| QI197 | QI197 | medium | defect | NOT_IMPLEMENTED | Insights applies axis filters only after truncating its findings |
| QI198 | QI198 | medium | defect | NOT_IMPLEMENTED | Creative-finding search links do not filter the finding cards |
| QI199 | QI199 | medium | defect | NOT_IMPLEMENTED | Insights does not apply later find-query navigation while mounted |
| QI200 | QI200 | medium | defect | NOT_IMPLEMENTED | A saved insight loses its success status when list refresh fails |
| QI201 | QI201 | medium | conditional_risk | NOT_IMPLEMENTED | Concurrent insight deletions overwrite each other’s pending indicator |
| QI202 | QI202 | medium | test_gap | NOT_IMPLEMENTED | The saved-view deletion test never verifies its claimed refresh persistence |
| QI203 | QI203 | medium | conditional_risk | NOT_IMPLEMENTED | Ask revenue bucketing turns accepted non-calendar labels into zero buckets |
| QI204 | QI204 | medium | defect | NOT_IMPLEMENTED | The Insights Date Saved filter leaves saved views unchanged |
| QI205 | QI205 | low | conditional_risk | NOT_IMPLEMENTED | Legacy AskBar accepts overlapping requests without a latest-answer guard |
| QI206 | QI206 | low | defect | NOT_IMPLEMENTED | Legacy Overview excludes a valid zero CPA from Best CPA |
| QI207 | QI207 | low | defect | NOT_IMPLEMENTED | Legacy Overview hides a measured zero ROAS as unavailable |
| QI208 | QI208 | low | conditional_risk | NOT_IMPLEMENTED | Legacy Overview and sync-job lists accept obsolete request completions |
| QI209 | QI209 | low | defect | NOT_IMPLEMENTED | Legacy XLSX upload has no keyboard-operable trigger |
| QI210 | QI210 | low | conditional_risk | NOT_IMPLEMENTED | ProviderLogo size attributes are overridden by fixed CSS dimensions |
| QI211 | QI211 | low | defect | NOT_IMPLEMENTED | Legacy sync-job load failures leave Loading Sync Jobs visible |
| QI212 | QI212 | low | defect | NOT_IMPLEMENTED | Legacy Overview keeps a stale sync-status failure after recovery |
| QI213 | QI213 | low | conditional_risk | NOT_IMPLEMENTED | Media-kind extension detection includes URL fragments |
| QI214 | QI214 | medium | conditional_risk | NOT_IMPLEMENTED | Detail media preview does not reload when only its nested source changes |
| QI215 | QI215 | medium | defect | NOT_IMPLEMENTED | Muted preview offers pointer-only play and pause controls |
| QI216 | QI216 | medium | test_gap | NOT_IMPLEMENTED | Dependency sync tests omit development declarations and version constraints |
| QI217 | QI217 | low | improvement | NOT_IMPLEMENTED | The test warning filter suppresses a whole category for one documented notice |
| QI218 | QI218 | low | improvement | NOT_IMPLEMENTED | Unused notification helper still claims to be shared by current screens |
| QI219 | QI219 | low | conditional_risk | NOT_IMPLEMENTED | Inactive preference parser accepts JSON null as a document |
| QI220 | QI220 | low | test_gap | NOT_IMPLEMENTED | The From-or-To regression test only exercises From |
| QI221 | QI221 | medium | defect | NOT_IMPLEMENTED | Applied UI language does not update the document language |
| QI222 | QI222 | low | improvement | NOT_IMPLEMENTED | Visual coverage descriptions count fourteen screens where only thirteen application routes are captured |
| QI223 | QI223 | low | improvement | NOT_IMPLEMENTED | The visual-review instructions refer to an undefined downloadable artifact |
| QI224 | QI224 | medium | test_gap | NOT_IMPLEMENTED | Screenshot acceptance can proceed before page content is ready |
| QI225 | QI225 | low | improvement | NOT_IMPLEMENTED | Legacy artwork comments promise more distinct variants than the generator supplies |
| QI226 | QI226 | medium | test_gap | NOT_IMPLEMENTED | Workbook visual test can accept a failed preview |
| QI227 | QI227 | medium | test_gap | NOT_IMPLEMENTED | Ask visual assertions do not establish the answer-content contract |
| QI251 | QI251,QI228 | low | improvement | NOT_IMPLEMENTED | SQLite test cleanup is not guaranteed after every acquisition |
| QI229 | QI229 | medium | defect | NOT_IMPLEMENTED | Legacy comparison fields lose their only visible labels after entry |
| QI230 | QI230 | medium | defect | NOT_IMPLEMENTED | Legacy dark-theme badges combine light text with light backgrounds |
| QI231 | QI231 | medium | defect | NOT_IMPLEMENTED | Legacy hover states reduce small control text contrast |
| QI232 | QI232 | medium | defect | NOT_IMPLEMENTED | Legacy retention labels and playhead use colors unsuited to dark mode |
| QI233 | QI233 | medium | defect | NOT_IMPLEMENTED | Legacy retention chart labels prefix records as the biggest drop |
| QI234 | QI234 | medium | defect | NOT_IMPLEMENTED | Legacy retention failures are displayed as missing data or no drops |
| QI235 | QI235 | medium | conditional_risk | NOT_IMPLEMENTED | Legacy filter refreshes can display older responses under newer filters |
| QI236 | QI236 | medium | conditional_risk | NOT_IMPLEMENTED | Legacy library and annotation actions can fail without visible feedback |
| QI237 | QI237 | medium | improvement | NOT_IMPLEMENTED | Legacy report downloads retain superseded Blob URLs |
| QI238 | QI238 | medium | defect | NOT_IMPLEMENTED | Legacy saved views omit the visible benchmark grouping |
| QI239 | QI239 | medium | defect | NOT_IMPLEMENTED | Legacy input focus styling replaces the visible outline with low-contrast colors |
| QI240 | QI240 | medium | defect | NOT_IMPLEMENTED | Legacy storyboard text is not adapted to dark mode |
| QI241 | QI241 | medium | defect | NOT_IMPLEMENTED | Legacy storyboard substitutes a thirty-second duration for missing or zero data |
| QI242 | QI242 | low | defect | NOT_IMPLEMENTED | Legacy fixture instructions reference a launcher absent from the pinned repository |
| QI243 | QI243 | medium | test_gap | NOT_IMPLEMENTED | Legacy ranking regression test checks source strings but not ranking behavior |
| QI244 | QI244 | medium | test_gap | NOT_IMPLEMENTED | Office export checks do not verify the downloaded document contents |
| QI245 | QI245 | medium | test_gap | NOT_IMPLEMENTED | CSV export checks omit field-quoting cases or numeric column values |
| QI246 | QI246 | low | improvement | NOT_IMPLEMENTED | Dependency parity documentation differs from current Creative Intelligence declarations |
| QI247 | QI247 | low | improvement | NOT_IMPLEMENTED | Historical coverage report incorrectly credits CSV self-checks for a missing workbook dependency path |
| QI248 | QI248 | low | improvement | NOT_IMPLEMENTED | The teardown comment incorrectly excludes autouse fixtures from unittest tests |
| QI249 | QI249 | medium | improvement | NOT_IMPLEMENTED | A failing teardown bypasses the shared cleanup call |
| QI250 | QI250 | low | improvement | NOT_IMPLEMENTED | Launch-test forced shutdown does not wait for the killed child |
| QI252 | QI252 | low | test_gap | NOT_IMPLEMENTED | The image-readiness timeout is passed as the browser predicate argument |
| QI253 | QI253 | medium | test_gap | NOT_IMPLEMENTED | A row-alignment assertion passes when it measures no grids |
| QI254 | QI254 | medium | test_gap | NOT_IMPLEMENTED | The natural-height mobile test checks only horizontal overflow |
| QI255 | QI255 | medium | test_gap | NOT_IMPLEMENTED | The mobile-control clipping check misses left and hidden-container clipping |
| QI256 | QI256 | medium | test_gap | NOT_IMPLEMENTED | The demo ROAS check accepts missing or incorrect positive values |
| QI257 | QI257 | medium | test_gap | NOT_IMPLEMENTED | The demo thumbnail check can overlook removed images and race lazy loading |
| QI258 | QI258 | low | test_gap | NOT_IMPLEMENTED | The focus-opening assertion starts with the tooltip already open |
| QI260 | QI260 | medium | conditional_risk | NOT_IMPLEMENTED | Unreadable successful JSON responses become fabricated empty objects |
| QI261 | QI261 | medium | conditional_risk | NOT_IMPLEMENTED | Binary downloads provide no application timeout or cancellation boundary |
| QI262 | QI262 | low | test_gap | NOT_IMPLEMENTED | Empty-input tests can pass on a later transport failure |
| QI263 | QI263 | high | conditional_risk | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Jobs whose leases expire after worker startup are not recovered by the polling loop |
| QI264 | QI264 | medium | conditional_risk | NOT_IMPLEMENTED | Late progress callbacks can overwrite a replacement attempt's progress |
| QI265 | QI265 | low | improvement | NOT_IMPLEMENTED | Job completion repeats the same return in both row-count branches |
| QI266 | QI266 | low | improvement | NOT_IMPLEMENTED | The attempt-state test docstring contradicts its cancelled-state case |
| QI267 | QI267 | medium | test_gap | NOT_IMPLEMENTED | The exact-date filter test accepts a result from the wrong day |
| QI268 | QI268 | medium | test_gap | NOT_IMPLEMENTED | Workbook section checks confuse global strings and archive entries with worksheet content |
| QI269 | QI269,QI270 | medium | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Comparison explanations reverse the paired values when the second creative leads |
| QI271 | QI271 | medium | defect | NOT_IMPLEMENTED | N-way comparison omits timed CTA annotations recognized elsewhere |
| QI272 | QI272 | low | improvement | NOT_IMPLEMENTED | N-way empty-data copy refers to only two creatives |
| QI273 | QI273 | medium | test_gap | NOT_IMPLEMENTED | The six-creative acceptance test exercises only three keys |
| QI274 | QI274 | medium | test_gap | NOT_IMPLEMENTED | SQL/Python scope parity accepts two equally wrong populations |
| QI275 | QI275 | low | improvement | NOT_IMPLEMENTED | The CPA ranking comment uses a scoped value for an unscoped query |
| QI276 | QI276 | medium | test_gap | NOT_IMPLEMENTED | Several analytical-answer tests omit their numeric facts |
| QI277 | QI277 | low | improvement | NOT_IMPLEMENTED | Test response helpers expose unused timeout parameters |
| QI278 | QI278 | medium | test_gap | NOT_IMPLEMENTED | The scoped why-analysis test exits before comparing campaign elements |
| QI279 | QI279 | medium | test_gap | NOT_IMPLEMENTED | Market-route tests accept the unfiltered campaign amount |
| QI281 | QI281 | low | test_gap | NOT_IMPLEMENTED | The report-rank option test searches outside its own control |
| QI282 | QI282 | medium | test_gap | NOT_IMPLEMENTED | The blank-quartile test can omit the wrong timestamp |
| QI283 | QI283 | medium | defect | NOT_IMPLEMENTED | A valid single-campaign report says its ranking metric is uncomputable |
| QI284 | QI284 | low | improvement | NOT_IMPLEMENTED | The acceptance-test header overstates what its fixtures prove |
| QI285 | QI285 | medium | test_gap | NOT_IMPLEMENTED | The invalid-rank test can pass after HTTP rank validation is removed |
| QI286 | QI286 | medium | test_gap | NOT_IMPLEMENTED | The thumbnail decode test checks only a signature and file size |
| QI287 | QI287 | low | improvement | NOT_IMPLEMENTED | The sample text-file check does not manage its open file lifetime |
| QI288 | QI288 | medium | defect | NOT_IMPLEMENTED | Brand-recall test plans select a retention metric as primary success |
| QI289 | QI289 | low | defect | NOT_IMPLEMENTED | Resume card labels the last-update date as the start date |
| QI290 | QI290 | low | defect | NOT_IMPLEMENTED | Findings flags and test verdicts bypass localization |
| QI291 | QI291 | medium | defect | NOT_IMPLEMENTED | Correction number fields can reject their supplied precision |
| QI292 | QI292 | medium | defect | NOT_IMPLEMENTED | Seek-button accessible names omit their visible moment descriptions |
| QI293 | QI293 | low | improvement | NOT_IMPLEMENTED | CSV placeholders point to a file chooser below instead of above |
| QI294 | QI294 | low | defect | NOT_IMPLEMENTED | Initial draft loading has no accessible status text |
| QI295 | QI295 | medium | conditional_risk | NOT_IMPLEMENTED | CSV candidate preview splits quoted multiline fields into separate rows |
| QI296 | QI296 | low | improvement | NOT_IMPLEMENTED | Error-helper comment describes the opposite envelope precedence |
| QI297 | QI297 | medium | test_gap | NOT_IMPLEMENTED | Presentation tests wait for static headings instead of their required data |
| QI298 | QI298 | low | improvement | NOT_IMPLEMENTED | The upload-card placement comment contradicts the dashboard composition |
| QI299 | QI299 | medium | test_gap | NOT_IMPLEMENTED | The narrow-card test never asserts that its controls stack |
| QI300 | QI300 | medium | test_gap | NOT_IMPLEMENTED | Dialog overflow checks omit the dialog bounds relative to the viewport |
| QI301 | QI301 | medium | defect | NOT_IMPLEMENTED | The mobile tooltip keeps the desktop bottom inset while JavaScript sets top |
| QI312 | QI312,QI302 | low | test_gap | NOT_IMPLEMENTED | Provider layout assertions omit header and position checks |
| QI304 | QI304 | low | improvement | NOT_IMPLEMENTED | Prompt-chip gap declaration is unconditionally replaced later in the stylesheet |
| QI305 | QI305 | low | improvement | NOT_IMPLEMENTED | Login card width comment does not match its asserted range |
| QI306 | QI306 | low | test_gap | NOT_IMPLEMENTED | Mobile login layout test omits horizontal logo centering |
| QI307 | QI307,QI308 | medium | defect | NOT_IMPLEMENTED | Friendly date labels use elapsed days instead of calendar days |
| QI309 | QI309 | medium | test_gap | NOT_IMPLEMENTED | Loading-announcement test checks a hiding class but not a live region |
| QI310 | QI310 | medium | test_gap | NOT_IMPLEMENTED | KPI sub-line test asserts only card titles |
| QI311 | QI311 | medium | conditional_risk | NOT_IMPLEMENTED | Dialog cards lack a vertical size and scrolling constraint |
| QI313 | QI313 | medium | conditional_risk | NOT_IMPLEMENTED | The stale-catalog tooltip trigger is not keyboard focusable |
| QI314 | QI314 | medium | conditional_risk | NOT_IMPLEMENTED | Filtering out the chosen model makes the controlled selector show no selection |
| QI315 | QI315 | high | conditional_risk | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Manual restore replaces current data before validating the replacement |
| QI316 | QI316 | low | improvement | NOT_IMPLEMENTED | Monotonic refresh timer carries an ineffective persistence setting |
| QI317 | QI317 | medium | test_gap | NOT_IMPLEMENTED | Migration regression test does not verify the claimed second-run no-op |
| QI318 | QI318 | low | improvement | NOT_IMPLEMENTED | Render manifest retains the deprecated automatic-deploy field |
| QI319 | QI319 | medium | test_gap | NOT_IMPLEMENTED | The worker-stop test never exercises stopping an active polling loop |
| QI320 | QI320 | medium | test_gap | NOT_IMPLEMENTED | The stale-result test claims full annotation preservation but checks only two fields |
| QI321 | QI321 | low | improvement | NOT_IMPLEMENTED | The video-validator reason-code documentation omits unsupported_container |
| QI322 | QI322 | medium | defect | NOT_IMPLEMENTED | Report assigns separate best and weakest labels to tied creatives |
| QI323 | QI323 | high | defect | LOCALLY_IMPLEMENTED_INTEGRATION_PENDING | Report test plans match rule IDs without retaining the creative |
| QI324 | QI324 | low | conditional_risk | NOT_IMPLEMENTED | Connector CSV cell helper omits standalone carriage returns from its quoting rule |
| QI325 | QI325 | low | defect | NOT_IMPLEMENTED | FocusTip loses visibility when one of its two active triggers ends |
| QI326 | QI326 | low | defect | NOT_IMPLEMENTED | Legacy secondary-button hover reduces normal-size text contrast |
| QI327 | QI327 | medium | defect | NOT_IMPLEMENTED | Creative-card badges pair near-white text with a near-white surface in dark mode |
| QI328 | QI328 | low | improvement | NOT_IMPLEMENTED | Static Top Creatives cards inherit a pointer cursor intended for interactive cards |
| QI329 | QI329 | medium | defect | NOT_IMPLEMENTED | Dimming enabled module choices lowers description-text contrast in both themes |
| QI330 | QI330 | medium | defect | NOT_IMPLEMENTED | Three effective report badge palettes fall below the small-text contrast benchmark |
| QI331 | QI331 | low | improvement | NOT_IMPLEMENTED | The compact Analyst badge rule is overridden in its verified consumer |
| QI332 | QI332 | medium | defect | NOT_IMPLEMENTED | Campaigns filter-toggle text has low declared contrast in both themes |
| QI333 | QI333 | low | defect | NOT_IMPLEMENTED | Opening the advanced disclosure restores its retired marker beside the SVG caret |
| QI334 | QI334 | low | improvement | NOT_IMPLEMENTED | The appended CSS overview overstates selector repetition and source-order precedence |
| QI335 | QI335 | low | improvement | NOT_IMPLEMENTED | Appearance sizing comment omits the equal flex bases in its mobile rule |
| QI336 | QI336 | low | improvement | NOT_IMPLEMENTED | Reports-control comment presents a wrapping row and minimum heights as fixed layout |
| QI337 | QI337 | low | conditional_risk | NOT_IMPLEMENTED | The first timestamp conversion pass bypasses the frame helper's recovery branch |

Status key: LOCALLY_IMPLEMENTED_INTEGRATION_PENDING = implemented pending
verification above; PARTIALLY_IMPLEMENTED = partial; NOT_IMPLEMENTED =
untouched. The ten highs in this push are pending verification. Original pin for every row:
`1342bb48ef59c45981c716c77d12898ae029daba`.

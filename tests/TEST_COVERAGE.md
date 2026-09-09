# Test Coverage — audit requirement to proving test

Scope: Expert 5 closeout. New audit file only; no source was edited.
Gate observed 2026-09-09 (macOS, Python 3.13.9, pytest 8.4.2):

- `python3 Source/self_check.py` — **93/93 checks passed**
- `python3 -m pytest tests/ -q` — **28 passed, 1 skipped**
  (skip: `IngestTest::test_excel_without_openpyxl_errors_clearly` —
  skips because `openpyxl` IS installed here; the error path it guards
  is covered by `Source/self_check.py` §14–15 ingest/quarantine checks.)

## Requirement map

| # | Audit requirement | Proving test(s) |
|---|---|---|
| 1 | Canonical schema v0 loads; four tables present | self_check §1 (schema version 0; four tables present) |
| 2 | Fixture loads as canonical rows; derived CPM/ROAS sane | self_check §2 (8 rows; cpm 3.0; roas 4.5) |
| 3 | Meta/TikTok source detection + header mapping, no unmapped | self_check §3 (meta/tiktok detected; maps to spend/impr/clicks/views/conv) |
| 4 | Row normalisation coerces numerics, defaults revenue | self_check §4 (spend float; revenue 0.0) |
| 5 | Benchmark min-n gate + pooled fallback for small cohorts | self_check §5 (insufficient + fallback_used); pytest `BenchmarkTest::test_spend_weighted_cpa`, `test_bad_group_rejected` |
| 6 | CPA ranking, best first, spend floor sinks | self_check §6; pytest `CrossEngineTest::test_source_backend_agree_on_ratios` |
| 7 | Annotations load, 7 verified / 1 draft in review (DD-001-A) | self_check §7; pytest `CreativeTest::test_blank_validates`, `test_bad_hook_rejected`, `test_verify_without_annotation_fails` |
| 8 | Metric join + element analysis (hook/CTA) + grounded recommendations | self_check §8 (join 7; CPA 2.0; early-beats-late; text hook; Shop now) |
| 9 | Report lineage: 64-hex deterministic hash, cohort filter, one-pager, CSV dump | self_check §9 (hash; 7 lower-funnel rows; spend 740; one-pager names GL-001-A + hash + formulas + learnings; CSV 8 rows); pytest `CreativeTest::test_pipeline_then_gate` (export gate end of pipeline) |
| 10 | Grounded Q&A: answers cite data; unknown topics refused | self_check §10 (hooks/tiktok/funnel/early/split/length/next grounded; radio refused); pytest `GroundedQATest` (all 5: empty refuses, cites Uploaded CSV first, both CTR zero-impression edges, review-to-zero) |
| 11 | Dashboard: valid HTML shell, theme toggle, badges, KPI + hash footer | self_check §11; self_check §16 escaping (hostile data/cohort escaped) |
| 12 | Providers: mock by default, Keychain-only keys (no values in status), Active/Fallback race fails closed, cue caps | self_check §12; pytest `ProviderPatternTest` (all 7: mock default, registry families, race prefer/fallback, race all-unavailable, cue caps, thinking params, sync due) |
| 13 | Deck export: six slides, grounded numbers, lineage footer, light-only print HTML | self_check §13 (six slides; GL-001-A + learnings; hash footer; totals 740.00; light-only); §16–17 (deck escaping, empty-cohort render). See Appendix B for PPTX verdict. |
| 14 | Per-source ingest: Meta 5+1, TikTok 5+1, Excel generic 4+0; 14 rows + 2 quarantined unify; ISO dates | self_check §14; pytest `IngestTest::test_meta_aliases`, `test_tiktok_aliases`, `test_insert_creates_creatives`, `test_load_fixtures_into_temp_db` |
| 15 | Validation quarantines bad date/spend/missing creative with reasons; accepted rows validate | self_check §15; pytest `IngestTest::test_garbage_and_nonfinite_quarantined`, `test_empty_csv_rejected`, `test_ingest_rejects_bad_payload` |
| 16 | Hardening: HTML escaping, non-finite spend quarantined, currency stripping, multi-day aggregation, empty/header-only/dir inputs | self_check §16 (all 12 checks) |
| 17 | Audit edges: hash mutation-sensitive, empty renders, stable ties, zero denominators, non-numeric seconds | self_check §17 (all 6 checks) |
| 18 | Backend API: ingest/annotate/verify/pipeline/retention actions; replay log round-trip; replay/run parity | pytest `ReplayTest::test_log_round_trip`; `IngestTest::test_ingest_rejects_bad_payload`; `RetentionTest::test_join_segments` |
| 19 | Export blocked until HUMAN-VERIFIED / reviews reach zero | pytest `CreativeTest::test_pipeline_then_gate`; `GroundedQATest::test_review_to_zero_gates_export` |
| 20 | No secrets in repo; Keychain-only keys | self_check §12 (status values <= configured/missing; no value longer than "configured"); repo rule, no `.env`/keys observed |
| 21 | Fixture path case consistency (`fixtures/` vs `Fixtures`) | Appendix A (documented, not renamed — rename breaks the other consumer) |
| 22 | Deck delivery format (real PPTX vs HTML-print) | Appendix B (HTML-print stands; rationale + smoke evidence) |

## Appendix A — fixtures/ vs Fixtures verdict: DOCUMENTED, not renamed

- On disk and in git: lowercase `fixtures/` (`git ls-files` shows
  `fixtures/Excel Sample.csv`, etc.).
- Consumers disagree: `Source/self_check.py` (§2, §7, §14) and `README.md`
  use lowercase `fixtures`; `Backend/server.py:20`
  (`FIXTURES = os.path.join(BASE, "Fixtures")`) uses capital-F `Fixtures`.
- This host's FS is case-insensitive, so both spellings resolve here and
  the full gate stays green — the mismatch is masked on macOS.
- On a case-sensitive FS (Linux/CI), `Fixtures/...` does not exist, and
  `load_fixtures()` silently skips every file
  (`if not os.path.exists(path): continue`) and returns 0, which turns
  `IngestTest::test_load_fixtures_into_temp_db` (`assertGreater(total, 0)`)
  red. Conversely, renaming the dir to `Fixtures` would break
  `self_check.py` §§2/7/14, which I may not edit (closeout owns new
  audit files only). So no rename was made.
- Recommended fix (one line, owner call): in `Backend/server.py:20`,
  change `"Fixtures"` to `"fixtures"` to match git, `self_check.py`,
  and `README.md`.

## Appendix B — PPTX probe verdict: HTML-print stands in

- Probe: `python-pptx 1.0.2` IS installed in this environment, and a smoke
  build (`Presentation` + title slide → `/tmp/pptx_smoke.pptx`, 28217 bytes)
  succeeded — real PPTX generation is technically possible.
- HTML-print stands because: (1) the repo contract is stdlib-only
  (`README.md` quickstart: "no dependencies"; pytest suite is stdlib
  `unittest`); adding a `python-pptx` dependency breaks that contract for
  every user. (2) The deck contract (`Source/deck.py` docstring +
  self_check §13) is light-only print-friendly HTML with lineage footer
  ("print to PDF for delivery"), and the one-pager/deck agreement checks
  pin that behavior — changing the format is a product decision plus a
  source edit, both outside closeout ownership (new audit files only).
- If a real `.pptx` is wanted later: add `python-pptx` as an optional
  export dependency behind the existing export gate, generate one slide
  per `slides()` tuple reusing the same grounded totals/benchmarks/hash,
  and extend §13 with a parity check (6 slides, GL-001-A, 740.00, hash).

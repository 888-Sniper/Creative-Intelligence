# Foap Analyst Traceability

Spec sections 3–20 to implementation files and tests. Starting SHA: `6429dd5`.

| Spec | Requirement | Implementation | Tests |
| ---- | ----------- | -------------- | ----- |
| 3 | Metric registry | `Backend/creative_intel/analyst_metrics.py` (`METRICS`, `DEFINITION_VERSION`) | `tests/test_analyst.py`, `tests/test_analyst_workbook.py` (Definitions sheet) |
| 3 | Calculation engine (deterministic, outside LLM) | `analyst_metrics.py` (`pooled_ratio`, `mean_of_rates`, `median_of_rates`, `awt_per_view`, `cpm`, `cpcv`, `cost_per_1000_reached`, `compare_groups`) | `tests/test_analyst.py` (acceptance table §19) |
| 3 | Creative annotation engine | `Backend/creative_intel/creative.py` (extended dimensions, human-correction guard) | existing creative tests + `tests/test_analyst.py` (classification) |
| 3 | Benchmark engine | `Backend/creative_intel/benchmarks.py` + analyst cohort/mean/median paths | `tests/test_cohorts_compare.py`, `tests/test_analyst.py` |
| 3 | Evidence engine | `Backend/creative_intel/analyst.py` (`analyze_campaign`, scope/dataset_version) | `tests/test_analyst.py` (scope isolation, export agreement) |
| 3 | Hypothesis engine | `Backend/creative_intel/analyst_diagnostics.py` (rule catalogue + combined patterns) | `tests/test_analyst.py` (rule trigger/non-trigger/insufficient-data) |
| 3 | Conversation layer | `Backend/creative_intel/analyst_chat.py` (owner-scoped conversations, memory, routing) | `tests/test_analyst_api.py` (turns, isolation, Polish journey) |
| 3 | Reporting layer | `analyst_chat.build_analyst_report`, `Backend/creative_intel/analyst_workbook.py` | `tests/test_analyst_api.py` (report), `tests/test_analyst_workbook.py` |
| 4 | Measurement families end-to-end | `Backend/creative_intel/schema.py`, `ingest.py`, `analyst_metrics.py` | `tests/test_analyst.py`, ingest/cohort tests |
| 4 | Platform semantics distinct | `analyst_metrics` (starts vs 2s/3s vs quartiles; watch bases) | `tests/test_analyst.py` (compatibility) |
| 4 | Polish import support | `ingest.py` (aliases, decimal commas, `przychod`, `wyswietlenia`…) | `tests/test_analyst.py` (Polish input) |
| 5 | Registry fields + tooltips/methodology | `METRICS` entries; methodology in report + Definitions sheet | workbook + report tests |
| 5 | Required calculations | `analyst_metrics.py` per-metric functions | `tests/test_analyst.py` (2s hook 30%, AWT 2.8s, 1.18/1.02 diff) |
| 5 | Aggregation safeguards | pooled vs mean vs median; no reach summing; SUMIFS parity in workbook | workbook agreement tests |
| 5 | Missing-data states | `field_state` (measured/missing/unsupported/estimated/not_applicable) | `tests/test_analyst.py` (low evidence) |
| 6 | Objective-aware analysis | `analyze_campaign(objective)`, `rank_creatives(rank_by)`, five-layer framing | objective ranking tests; Polish journey |
| 7 | Creative classifications | `creative.py` dimensions (opening, hook, format, message, promotion, narrative, execution, concept) | classification tests |
| 8 | Retention/brand limits | quartile-resolution evidence; no brand-recall invention | retention + brand tests |
| 9 | Benchmark scopes | same scope across dashboard/compare/analyst/exports; duration groups | scope isolation tests |
| 10 | Structured findings | finding objects with traceability + uncertainty fields | finding persistence/decision API tests |
| 11 | Diagnostic catalogue | `analyst_diagnostics.py` (28 single-metric + Hook+Hold, 25%+completion, CPM+CPCV combos) | trigger/non-trigger/insufficient-data per rule |
| 12 | Evidence/correlation layer | `compare_groups` (independent creative units, exploratory 3/6 convention, guardrails) | correlation safeguard tests |
| 13 | Recommendations + test plans | `recommendations_from_findings`, `test_plan_for_finding`, cap of 3 | rec/test tests; Polish condense journey |
| 14 | Persistent conversations | `analyst_chat` conversations/messages/findings tables, owner isolation | API tests (history, isolation, scope change) |
| 15 | Polish follow-ups | task routing, locale-aware formatting (`1,18 s`), headline rewrite, analyst-note labelling | 7-step Polish journey tests |
| 16 | Grounding | engine-only numbers; evidence IDs; untrusted-content boundaries | grounding tests |
| 17 | UI + exports | `AnalystPage.tsx`, routes `/api/analyst/report`, `/api/analyst/workbook`, SPA fallback | vitest (4), e2e `analyst.spec.ts`, API export tests |
| 17 | Blank workbook | `analyst_workbook.py` (A6, 200 rows, M–T, 7 sheets, registry formulas) | `tests/test_analyst_workbook.py` (9 tests incl. engine agreement) |
| 18 | Safeguards | job worker analyst path, leases, cancellation, rate limits, CSRF, audit | job/API/security suites |
| 19 | Acceptance table | synthetic fixtures incl. labelled 1.18s/1.02s | `tests/test_analyst.py` |
| 20 | Foap conversation E2E | 7-step Polish journey via app components + authorized sessions | API journey tests; simulated providers only (not live validation) |

Evidence boundary: quoted watch-time values and example creatives appear only in
labelled test fixtures, never as real data. No universal marketing thresholds are
embedded; workbook/app thresholds compare against the cohort benchmark.

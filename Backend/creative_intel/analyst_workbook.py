"""Foap Analyst reusable blank workbook (spec section 17).

Seven sheets — Input, Metrics, Benchmarks, Hypotheses, Creative
Summary, Test Plan, Definitions — with spreadsheet formulas generated
from the shared metric registry (analyst_metrics.METRICS), so the
workbook recalculates offline with no credentials. The application
itself has no creative-count limit; only this reusable template
reserves 200 input rows.

Layout contract (tested):
- Input data starts at A6 (rows 1-4 title/meta, row 5 headers).
- 200 creative rows (6..205). Required metric inputs in A-L,
  optional creative context in M-T.
- Metrics rows mirror Input rows with per-row formulas.
- Benchmarks aggregates the full 200-row ranges (pooled numerators
  and denominators first — never an average of daily percentages).
- Hypotheses are rule-based candidate suggestions only, clearly
  labelled as such; richer AI-written analysis needs the app.
"""

from __future__ import annotations

from creative_intel import analyst_metrics as metrics_mod
from creative_intel import ooxml

HEADER_ROW = 5
FIRST_DATA_ROW = 6
N_ROWS = 200
LAST_DATA_ROW = FIRST_DATA_ROW + N_ROWS - 1  # 205

# (column letter, input field, header label)
INPUT_COLUMNS = [
    ("A", "creative_key", "Creative"),
    ("B", "impressions", "Impressions"),
    ("C", "reach", "Reach (unique, as reported)"),
    ("D", "video_starts", "Video starts"),
    ("E", "views_2s", "2s views"),
    ("F", "views_3s", "3s views"),
    ("G", "views_25", "25% views"),
    ("H", "views_50", "50% views"),
    ("I", "views_75", "75% views"),
    ("J", "views_100", "100% views (completions)"),
    ("K", "watch_time_total_s", "Watch time total (s)"),
    ("L", "spend", "Spend"),
    ("M", "duration_s", "Duration (s)"),
    ("N", "creator", "Creator"),
    ("O", "concept", "Concept / angle"),
    ("P", "format", "Format"),
    ("Q", "message", "Message (promotional/neutral/mixed/unknown)"),
    ("R", "promotion", "Promotion"),
    ("S", "opening_delivery", "Opening delivery"),
    ("T", "notes", "Notes"),
]

INPUT_FIELD_COL = {field: col for col, field, _ in INPUT_COLUMNS}

NA = '"n/a"'


def _ratio_formula(num_ref, den_ref):
    """Percent ratio with missing/zero guards; never divides blindly."""
    return ("IF(OR(%s=\"\",%s=\"\",%s=0),%s,%s/%s*100)"
            % (num_ref, den_ref, den_ref, NA, num_ref, den_ref))


def _input_ref(field, row):
    return "Input!%s%d" % (INPUT_FIELD_COL[field], row)


# Metrics sheet columns: (letter, metric_id or None, header). The
# numerator/denominator Input columns come from the shared registry
# entry for that metric_id where the registry names concrete fields.
METRIC_COLUMNS = [
    ("A", None, "Creative"),
    ("B", "hook_rate_2s_impr", "2s Hook Rate % (2s views ÷ impressions)"),
    ("C", "hook_rate_3s_impr", "3s Hook Rate % (3s views ÷ impressions)"),
    ("D", "hold_25_over_3s", "Hold % (25% views ÷ 3s views; needs duration ≥ 12 s)"),
    ("E", "quartile_25_impr", "25% viewing % (÷ impressions)"),
    ("F", "quartile_50_impr", "50% viewing % (÷ impressions)"),
    ("G", "vtr", "VTR % (completions ÷ impressions)"),
    ("H", "awt_starts", "AWT s (watch ÷ video starts; starts-basis sources)"),
    ("I", "awt_pct_duration", "AWT % of own duration"),
    ("J", "cpm", "CPM (spend ÷ impressions × 1000; single currency)"),
    ("K", "cpcv", "CPCV (spend ÷ completions)"),
    ("L", "cost_per_1000_reached", "Cost per 1000 reached"),
]

# Registry metric -> (numerator input field, denominator input field).
# Hold has no universal registry formula by design (spec section 5):
# this workbook fixes ONE explicit variant and labels it as such.
WORKBOOK_RATIOS = {
    "hook_rate_2s_impr": ("views_2s", "impressions"),
    "hook_rate_3s_impr": ("views_3s", "impressions"),
    "hold_25_over_3s": ("views_25", "views_3s"),
    "quartile_25_impr": ("views_25", "impressions"),
    "quartile_50_impr": ("views_50", "impressions"),
    "vtr": ("views_100", "impressions"),
    "cpm": ("spend", "impressions"),
    "cpcv": ("spend", "views_100"),
    "cost_per_1000_reached": ("spend", "reach"),
}

# Metrics-sheet column letter per ratio metric (for Benchmarks refs).
METRIC_COL = {mid: col for col, mid, _ in METRIC_COLUMNS if mid}


def metric_cell_formula(metric_id, row):
    """Spreadsheet formula for one Metrics cell, from registry fields."""
    if metric_id is None:
        return 'IF(Input!A%d="","",Input!A%d)' % (row, row)
    if metric_id in WORKBOOK_RATIOS:
        num, den = WORKBOOK_RATIOS[metric_id]
        scale = 1000 if metric_id in ("cpm", "cost_per_1000_reached") \
            else (1 if metric_id == "cpcv" else 100)
        formula = _ratio_formula(_input_ref(num, row), _input_ref(den, row))
        if scale != 100:
            formula = formula.replace("*100", "" if scale == 1 else "*1000")
        if metric_id == "hold_25_over_3s":
            dur = _input_ref("duration_s", row)
            formula = ("IF(AND(%s<>\"\",%s<12),\"n/a (25%% before 3s)\",%s)"
                       % (dur, dur, formula))
        return formula
    if metric_id == "awt_starts":
        watch, starts = _input_ref("watch_time_total_s", row), \
            _input_ref("video_starts", row)
        return ("IF(OR(%s=\"\",%s=\"\",%s=0),%s,%s/%s)"
                % (watch, starts, starts, NA, watch, starts))
    if metric_id == "awt_pct_duration":
        awt = "Metrics!H%d" % row
        dur = _input_ref("duration_s", row)
        return ("IF(OR(%s=%s,%s=\"\",%s=0),%s,%s/%s*100)"
                % (awt, NA, dur, dur, NA, awt, dur))
    raise ValueError("no workbook formula for %s" % metric_id)


BENCHMARK_ROWS = [
    # (label, metric_id for pooled numerator/denominator or None)
    ("2s Hook Rate %", "hook_rate_2s_impr"),
    ("3s Hook Rate %", "hook_rate_3s_impr"),
    ("Hold % (25% ÷ 3s)", "hold_25_over_3s"),
    ("25% viewing %", "quartile_25_impr"),
    ("50% viewing %", "quartile_50_impr"),
    ("VTR %", "vtr"),
    ("AWT s", None),
    ("AWT % of duration", None),
    ("CPM", "cpm"),
    ("CPCV", "cpcv"),
    ("Cost per 1000 reached", "cost_per_1000_reached"),
]


def _benchmark_formulas(metric_id, mcol):
    """(pooled, mean, median, n) formulas for one benchmark row.

    Pooled re-sums compatible numerators/denominators over the whole
    Input range; mean/median read the per-creative Metrics column
    (AVERAGE/MEDIAN ignore the "n/a" text). Reach is never summed:
    pooled cost-per-1000-reached is spend over reach only when the
    Input reach values describe non-overlapping groups — the sheet
    labels this assumption.
    """
    rng = "%s%d:%s%d" % (mcol, FIRST_DATA_ROW, mcol, LAST_DATA_ROW)
    mean = "AVERAGE(Metrics!%s)" % rng
    median = "MEDIAN(Metrics!%s)" % rng
    count = "COUNT(Metrics!%s)" % rng
    if metric_id in WORKBOOK_RATIOS:
        num, den = WORKBOOK_RATIOS[metric_id]
        scale = 1000 if metric_id in ("cpm", "cost_per_1000_reached") \
            else (1 if metric_id == "cpcv" else 100)
        ncol = INPUT_FIELD_COL[num]
        dcol = INPUT_FIELD_COL[den]
        nrng = "Input!%s%d:%s%d" % (ncol, FIRST_DATA_ROW, ncol,
                                    LAST_DATA_ROW)
        drng = "Input!%s%d:%s%d" % (dcol, FIRST_DATA_ROW, dcol,
                                    LAST_DATA_ROW)
        # Mirror the engine: rows missing either side are excluded from
        # BOTH sums (missing is never a zero). Measured zeros stay in.
        num_sum = "SUMIFS(%s,%s,\"<>\",%s,\"<>\")" % (nrng, nrng, drng)
        den_sum = "SUMIFS(%s,%s,\"<>\",%s,\"<>\")" % (drng, nrng, drng)
        pooled = ("IF(%s=0,\"n/a\",%s/%s%s)"
                  % (den_sum, num_sum, den_sum,
                     "" if scale == 1 else "*%d" % scale))
    else:
        pooled = '"see mean/median (no pooled basis)"'
    return pooled, mean, median, count


# Rule-based candidate hypotheses: (signal column, rule id, text).
# Thresholds compare against the Benchmarks pooled row ($B) — no
# universal marketing constants embedded.
HYPOTHESIS_RULES = [
    ("B", "low_hook",
     "Candidate: opening may not establish attention/context. "
     "Iteration: test 3-5 alternative openings."),
    ("C", "weak_hold",
     "Candidate: body may not develop the opening promise. "
     "Iteration: preserve hook; shorten setup."),
]


def hypothesis_formula(rule_id, row):
    # Benchmarks data rows start at FIRST_DATA_ROW in BENCHMARK_ROWS
    # order: 2s hook -> row 6, hold -> row 8.
    hook = "Metrics!B%d" % row
    bench = "Benchmarks!B$%d" % FIRST_DATA_ROW
    if rule_id == "low_hook":
        return ("IF(OR(%s=\"n/a\",%s=\"n/a\"),\"insufficient data\","
                "IF(%s<%s*0.8,\"Candidate: LOW 2s retention — %s\","
                "\"hook OK\"))"
                % (hook, bench, hook, bench,
                   "opening may not establish attention"))
    if rule_id == "weak_hold":
        hold = "Metrics!D%d" % row
        hook3 = "Metrics!C%d" % row
        hold_bench = "Benchmarks!B$%d" % (FIRST_DATA_ROW + 2)
        return ("IF(OR(%s=\"n/a\",%s=\"n/a\",%s=\"n/a\"),\"insufficient data\","
                "IF(AND(%s>=%s*0.8,%s<%s*0.8),\"high hook / weak hold — %s\","
                "\"hold OK or hook first\"))"
                % (hook3, hold, hold_bench, hook3, bench, hold,
                   hold_bench, "body may not develop the opening promise"))
    raise ValueError("unknown rule %s" % rule_id)


BENCHMARK_METRIC_COL = {
    "hook_rate_2s_impr": "B", "hook_rate_3s_impr": "C",
    "hold_25_over_3s": "D", "quartile_25_impr": "E",
    "quartile_50_impr": "F", "vtr": "G", None: "H",
}

def _title_block(title, lines):
    # Exactly HEADER_ROW - 1 rows so headers land on HEADER_ROW (5)
    # and data starts at FIRST_DATA_ROW (6).
    rows = [[title]]
    rows += [[line] for line in lines[:HEADER_ROW - 2]]
    while len(rows) < HEADER_ROW - 1:
        rows.append([""])
    return rows[:HEADER_ROW - 1]


def _input_sheet(prefill):
    rows = _title_block("Foap Analyst — Input (RAW DATA)", [
        "Paste one creative per row starting at row %d. Do not insert rows above."
        % FIRST_DATA_ROW,
        "Reach is unique reach as reported — never summed across overlapping groups.",
        "Watch time basis: video starts. Per-user watch sources are unsupported here; use the app.",
        "Single currency per workbook. Blank = missing (never a measured zero).",
    ])
    rows.append([label for _, _, label in INPUT_COLUMNS])
    by_key = dict(prefill or {})
    order = [r[0] for r in (prefill or [])] if isinstance(prefill, list) \
        else list(by_key)
    for i in range(N_ROWS):
        key = order[i] if i < len(order) else ""
        values = by_key.get(key, {}) if key else {}
        rows.append([values.get(field, key if field == "creative_key" else "")
                     for _, field, _ in INPUT_COLUMNS])
    return {"name": "Input", "header": [], "rows": rows}


def _metrics_sheet():
    rows = _title_block("Metrics & calculations (from shared definitions)", [
        "Every formula below is generated from the metric registry — see Definitions.",
        "Hold uses ONE explicit variant (25%% ÷ 3s views, duration ≥ 12 s) and labels it.",
    ])
    rows.append([header for _, _, header in METRIC_COLUMNS])
    for row in range(FIRST_DATA_ROW, LAST_DATA_ROW + 1):
        rows.append([{"formula": metric_cell_formula(mid, row)}
                     for _, mid, _ in METRIC_COLUMNS])
    return {"name": "Metrics", "header": [], "rows": rows}


def _benchmarks_sheet():
    rows = _title_block("Benchmarks (campaign cohort in this workbook)", [
        "Pooled re-sums numerators/denominators over all 200 rows.",
        "Mean/median read per-creative Metrics (text 'n/a' is ignored).",
        "Pooled cost-per-1000-reached assumes non-overlapping reach groups.",
    ])
    rows.append(["Metric", "Pooled", "Mean of creatives", "Median", "n"])
    for label, mid in BENCHMARK_ROWS:
        if mid in BENCHMARK_METRIC_COL:
            mcol = BENCHMARK_METRIC_COL[mid]
        else:
            mcol = "H" if label == "AWT s" else "I"
        pooled, mean, median, count = _benchmark_formulas(mid, mcol)
        rows.append([label, {"formula": pooled}, {"formula": mean},
                     {"formula": median}, {"formula": count}])
    return {"name": "Benchmarks", "header": [], "rows": rows}


def _hypotheses_sheet():
    rows = _title_block("Hypotheses (RULE-BASED candidates — not AI analysis)", [
        "Thresholds compare each creative to this workbook's own pooled benchmark.",
        "Treat every row as plausible, never proven. Richer AI-written analysis needs the app.",
    ])
    rows.append(["Creative", "Stop: hook check", "Hold: hook/body check",
                 "Preserve", "Change"])
    for row in range(FIRST_DATA_ROW, LAST_DATA_ROW + 1):
        rows.append([{"formula": 'IF(Input!A%d="","",Input!A%d)' % (row, row)},
                     {"formula": hypothesis_formula("low_hook", row)},
                     {"formula": hypothesis_formula("weak_hold", row)},
                     "body/hook whichever scores better",
                     "losing element per the two checks"])
    return {"name": "Hypotheses", "header": [], "rows": rows}


def _summary_sheet():
    rows = _title_block("Creative Summary (five layers)", [
        "Stop / Hold / Depth read Metrics; Brand reads your Input context (M-T);",
        "Efficiency reads cost columns. Fill Brand from actual observations only.",
    ])
    rows.append(["Creative", "Stop (2s hook %)", "Hold (hold %)",
                 "Depth (VTR %)", "Brand (from Input M-T)", "Efficiency (CPM)",
                 "Duration (s)", "Message", "Opening"])
    for row in range(FIRST_DATA_ROW, LAST_DATA_ROW + 1):
        rows.append([
            {"formula": 'IF(Input!A%d="","",Input!A%d)' % (row, row)},
            {"formula": "Metrics!B%d" % row},
            {"formula": "Metrics!D%d" % row},
            {"formula": "Metrics!G%d" % row},
            {"formula": 'IF(Input!A%d="","",Input!Q%d&" / "&Input!S%d)'
             % (row, row, row)},
            {"formula": "Metrics!J%d" % row},
            {"formula": 'IF(Input!A%d="","",Input!M%d)' % (row, row)},
            {"formula": 'IF(Input!A%d="","",Input!Q%d)' % (row, row)},
            {"formula": 'IF(Input!A%d="","",Input!S%d)' % (row, row)},
        ])
    return {"name": "Creative Summary", "header": [], "rows": rows}


def _test_plan_sheet():
    rows = _title_block("Test Plan (controlled next tests)", [
        "One variable per test. Reach tests optimise attention metrics, not clicks.",
        "No uplift is promised. Keep losing variants in the learning history.",
    ])
    rows.append(["Hypothesis", "Control creative", "Proposed variant",
                 "Variable changed", "Held constant", "Objective",
                 "Primary metric", "Guardrails", "Evaluation", "Limitations"])
    rows.append(["EXAMPLE (delete me): opening drives stop",
                 "Creative A", "A with 3 new first-2s openings",
                 "first 2 seconds only", "body, CTA, audience, budget",
                 "reach", "2s Hook Rate %", "CPM, frequency",
                 "same scope, 1 flight", "example row, not evidence"])
    for _ in range(19):
        rows.append([""] * 10)
    return {"name": "Test Plan", "header": [], "rows": rows}


def _definitions_sheet():
    rows = _title_block("Definitions (shared metric registry v%s)"
                        % metrics_mod.DEFINITION_VERSION, [
        "Data states: measured / missing / unsupported / estimated / not_applicable.",
        "Blank Input = missing, never zero. CTR/CVR/CPA/ROAS need click/conversion",
        "columns beyond this workbook — use the app import for those.",
    ])
    rows.append(["metric_id", "EN", "PL", "numerator", "denominator",
                 "unit", "direction", "aggregation", "requires"])
    for mid, spec in metrics_mod.METRICS.items():
        rows.append([mid, spec.get("display", {}).get("en", ""),
                     spec.get("display", {}).get("pl", ""),
                     str(spec.get("numerator")),
                     str(spec.get("denominator")), str(spec.get("unit")),
                     str(spec.get("direction")),
                     str(spec.get("aggregation")),
                     ",".join(spec.get("requires", ()))])
    return {"name": "Definitions", "header": [], "rows": rows}


def build_blank_workbook(prefill=None):
    """Blank reusable workbook as .xlsx bytes.

    prefill: optional list of (creative_key, {input_field: value}) used
    by tests to fill Input rows; production callers omit it.
    """
    sheets = [_input_sheet(prefill), _metrics_sheet(),
              _benchmarks_sheet(), _hypotheses_sheet(),
              _summary_sheet(), _test_plan_sheet(),
              _definitions_sheet()]
    return ooxml.build_xlsx(sheets)

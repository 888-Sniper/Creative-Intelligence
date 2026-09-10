"""Foap Analyst: objective-aware creative analysis over uploaded data.

Pipeline plumbing (per conversation turn):

  scope + objective -> scoped ads rows -> per-creative pooled metrics
  (analyst_metrics) -> cohort bands -> diagnostics catalogue
  (analyst_diagnostics) -> findings -> recommendations / test plans.

Every number comes from the shared calculation engine; the LLM is
never in the numeric path. Findings persist per conversation with
scope + dataset version so changed filters recompute visibly.
"""

from __future__ import annotations

import json

from creative_intel import analyst_diagnostics as diagnostics
from creative_intel import analyst_metrics as metrics
from creative_intel import benchmarks
from creative_intel import creative as creative_mod
from creative_intel import retention as retention_mod

OBJECTIVES = ("reach", "conversions")

DEFAULT_RANK = {"reach": "hook_rate_2s_impr", "conversions": "cpa"}

EXTRA_SCOPE_KEYS = ("placement", "audience", "campaign_id", "ad_id",
                    "account_id", "creator", "concept", "format",
                    "message_class", "promotion")


def dataset_version(conn):
    """Dataset fingerprint: row count + newest import timestamp."""
    try:
        count = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    except Exception:
        count = 0
    try:
        latest = conn.execute("SELECT MAX(created_at) FROM"
                              " analyst_imports").fetchone()[0]
    except Exception:
        latest = None
    return "ads=%d@%s" % (count, latest or "no-imports")


def scoped_rows(conn, scope):
    """Ads rows inside the shared Scope plus analyst extra keys."""
    scope_obj = (scope if isinstance(scope, benchmarks.Scope)
                 else benchmarks.Scope(scope))
    extras = {}
    if isinstance(scope, dict):
        for key in EXTRA_SCOPE_KEYS:
            vals = [v for v in benchmarks._as_list(scope.get(key))
                    if v not in ("", "all", None)]
            if vals:
                extras[key] = [str(v).lower() for v in vals]
    rows = []
    for row in benchmarks.all_rows(conn):
        if not scope_obj.match(row):
            continue
        ok = True
        for key, vals in extras.items():
            if str(row.get(key) or "").lower() not in vals:
                ok = False
                break
        if ok:
            rows.append(row)
    return rows, scope_obj


def durations_for(conn, creative_keys):
    """Creative durations in seconds keyed by creative_key."""
    out = {}
    for key in creative_keys:
        row = conn.execute("SELECT duration_s FROM creatives"
                           " WHERE creative_key=?", (key,)).fetchone()
        try:
            out[key] = float((row or [0])[0] or 0)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def annotations_for(conn, creative_keys):
    """Latest annotations + status keyed by creative_key."""
    out = {}
    for key in creative_keys:
        row = conn.execute("SELECT annotation_json FROM annotations"
                           " WHERE creative_key=?", (key,)).fetchone()
        if not row:
            out[key] = (None, "none")
            continue
        try:
            ann = json.loads(row[0])
        except (ValueError, TypeError):
            out[key] = (None, "none")
            continue
        status = "human_verified" if ann.get("status") == \
            "human_verified" else "auto"
        out[key] = (ann, status)
    return out


def _hold_choice(rows, duration_s):
    """Best compatible hold definition for these rows.

    Prefers 25%-over-3s only when the quartile threshold actually
    falls after three seconds (0.25 * duration > 3); a 25%-of-6s
    numerator can never pose as post-3s retention. Falls back to
    100%-over-25%, then 50%-over-25%.
    """
    candidates = []
    if duration_s and duration_s > 0 and 0.25 * duration_s > 3:
        candidates.append(("views_25", "views_3s"))
    candidates.extend([("views_100", "views_25"),
                       ("views_50", "views_25")])
    for num, den in candidates:
        num_state, _ = metrics.field_state(rows, num)
        den_state, _ = metrics.field_state(rows, den)
        if num_state != metrics.UNSUPPORTED and \
                den_state != metrics.UNSUPPORTED:
            return num, den
    return candidates[0]


def creative_metrics(rows, duration_s=0):
    """All registry metrics computable for one creative's rows."""
    out = {}
    out["hook_rate_2s_impr"] = metrics.hook_rate_2s(rows)
    out["hook_rate_3s_impr"] = metrics.hook_rate_3s(rows)
    num, den = _hold_choice(rows, duration_s)
    out["hold_rate"] = metrics.hold_rate(rows, num, den)
    out["quartile_25_impr"] = metrics.pooled_ratio(
        rows, "quartile_25_impr", "views_25", "impressions")
    out["quartile_50_impr"] = metrics.pooled_ratio(
        rows, "quartile_50_impr", "views_50", "impressions")
    out["quartile_75_impr"] = metrics.pooled_ratio(
        rows, "quartile_75_impr", "views_75", "impressions")
    out["completion_impr"] = metrics.pooled_ratio(
        rows, "completion_impr", "views_100", "impressions")
    out["vtr"] = metrics.pooled_ratio(rows, "vtr", "views_100",
                                      "impressions")
    awt, pct = metrics.awt_per_view(
        rows, {rows[0].get("creative_key", ""): duration_s} if rows
        else {})
    out["awt_per_view"] = awt
    out["awt_pct_duration"] = pct
    out["cpm"] = metrics.cpm(rows)
    out["cpcv"] = metrics.cpcv(rows)
    out["cost_per_1000_reached"] = metrics.cost_per_1000_reached(rows)
    out["frequency"] = metrics.frequency(rows)
    out["ctr_link"] = metrics.pooled_ratio(rows, "ctr_link",
                                           "link_clicks", "impressions")
    out["ctr_all"] = metrics.pooled_ratio(rows, "ctr_all", "clicks",
                                          "impressions")
    out["cvr"] = metrics.pooled_ratio(rows, "cvr", "conversions",
                                      "link_clicks")
    out["cpa"] = metrics.pooled_ratio(rows, "cpa", "spend",
                                      "conversions", scale=1.0)
    out["roas"] = metrics.pooled_ratio(rows, "roas", "revenue",
                                       "spend", scale=1.0)
    if out["roas"]["state"] in (metrics.MEASURED, metrics.ESTIMATED):
        reported = any(bool(r.get("revenue_reported")) for r in rows)
        if not reported:
            # Honest null beats a flagged-zero: unreported revenue must
            # never render as ROAS 0.0, estimated or otherwise.
            out["roas"]["value"] = None
            out["roas"]["state"] = metrics.UNSUPPORTED
            out["roas"]["numerator"] = 0.0
            out["roas"]["denominator"] = 0.0
            out["roas"]["reasons"] = \
                list(out["roas"]["reasons"]) + \
                ["revenue not flagged reported in this scope"]
    out["engagement_rate"] = metrics.engagement_rate(rows)
    out["exposure"] = {"impressions": sum(
        metrics._num(r, "impressions") for r in rows),
        "spend": sum(metrics._num(r, "spend") for r in rows)}
    return out


def _series_for(rows):
    """Date-ordered per-day aggregates for fatigue/scale rules."""
    by_date = {}
    for row in rows:
        by_date.setdefault(row.get("date") or "", []).append(row)
    series = []
    for date in sorted(d for d in by_date if d):
        day = by_date[date]
        freq = metrics.frequency(day)
        vtr = metrics.pooled_ratio(day, "vtr", "views_100",
                                   "impressions")
        cpa = metrics.pooled_ratio(day, "cpa", "spend", "conversions",
                                   scale=1.0)
        series.append({"date": date, "frequency": freq, "vtr": vtr,
                       "cpa": cpa,
                       "spend": sum(metrics._num(r, "spend")
                                    for r in day)})
    return series


def analyze_campaign(conn, scope, objective="reach"):
    """Full deterministic analysis for one scope + objective.

    Returns {"creatives": [...], "cohort_findings": [...],
    "scope": ..., "dataset_version": ..., "objective": ...} where each
    creative carries metrics, findings, five-layer summary,
    annotation, durations and limitations. No LLM in this path.
    """
    objective = objective if objective in OBJECTIVES else "reach"
    rows, scope_obj = scoped_rows(conn, scope)
    version = dataset_version(conn)
    scope_desc = scope_obj.describe()
    if not rows:
        return {"creatives": [], "cohort_findings": [],
                "scope": scope_desc,
                "scope_detail": dict(scope_obj.axes),
                "dataset_version": version, "objective": objective,
                "empty_reason": "no uploaded rows match this scope"}
    by_creative = {}
    for row in rows:
        by_creative.setdefault(row.get("creative_key") or "", []).append(
            row)
    keys = sorted(by_creative)
    durations = durations_for(conn, keys)
    annotations = annotations_for(conn, keys)
    per_creative_metrics = {
        key: creative_metrics(grows, durations.get(key, 0))
        for key, grows in by_creative.items()}
    # Cohort bands per metric across creatives (measured only).
    cohort = {}
    for mid in next(iter(per_creative_metrics.values()), {}):
        if mid == "exposure":
            continue
        vals = [m[mid]["value"] for m in per_creative_metrics.values()
                if diagnostics._measured(m.get(mid))]
        cohort[mid] = vals
    creatives = []
    for key in keys:
        grows = by_creative[key]
        ann, ann_status = annotations[key]
        try:
            drops = retention_mod.drop_events(conn, key)
        except Exception:
            drops = []
        ctx = {"creative_key": key,
               "metrics": per_creative_metrics[key],
               "cohort": cohort,
               "cohort_n": len(keys),
               "exposure": per_creative_metrics[key]["exposure"][
                   "impressions"],
               "spend": per_creative_metrics[key]["exposure"]["spend"],
               "cohort_spend": [per_creative_metrics[k]["exposure"][
                   "spend"] for k in keys],
               "annotation": ann,
               "annotation_status": ann_status,
               "retention_drops": drops,
               "series": _series_for(grows),
               "duration_s": durations.get(key, 0),
               "objective": objective,
               "scope": {"describe": scope_desc,
                         "detail": dict(scope_obj.axes)},
               "dataset_version": version}
        findings, suppressed = diagnostics.evaluate_creative(ctx)
        layers = diagnostics.five_layer_summary(ctx, findings)
        message_class = creative_mod.message_class_of(
            ann, grows[0] if grows else None)
        creatives.append({"creative_key": key,
                          "name": (grows[0].get("ad_name") or ""),
                          "platform": (grows[0].get("platform") or ""),
                          "campaign": (grows[0].get("campaign") or ""),
                          "duration_s": durations.get(key, 0),
                          "message_class": message_class,
                          "format_kind": (ann or {}).get(
                              "format_kind", "unknown"),
                          "opening_delivery": (ann or {}).get(
                              "opening_delivery", "unknown"),
                          "metrics": per_creative_metrics[key],
                          "rows": len(grows),
                          "exposure": per_creative_metrics[key][
                              "exposure"],
                          "findings": findings,
                          "suppressed": suppressed,
                          "layers": layers,
                          "annotation_status": ann_status,
                          "brand": creative_mod.brand_evidence_summary(
                              ann)})
    summaries = [{"creative_key": c["creative_key"],
                  "metrics": c["metrics"],
                  "duration_s": c["duration_s"],
                  "format_kind": c["format_kind"],
                  "opening_delivery": c["opening_delivery"]}
                 for c in creatives]
    rows_by_key = dict(by_creative)
    scope_info = {"describe": scope_desc, "detail": dict(scope_obj.axes)}
    cohort_findings = diagnostics.rule_format_comparison(
        summaries, rows_by_key, scope_info, version, objective)
    duration_roles = diagnostics.rule_duration_roles(
        summaries, scope_info, version)
    if duration_roles is not None:
        cohort_findings.append(duration_roles)
    return {"creatives": creatives, "cohort_findings": cohort_findings,
            "scope": scope_desc, "scope_detail": dict(scope_obj.axes),
            "dataset_version": version, "objective": objective,
            "empty_reason": None}


def rank_creatives(analysis, rank_by=None):
    """Objective-aware ranking; explicit KPI always wins.

    Reach never defaults to CPA merely because conversions exist.
    Winners need a measured value and minimum exposure; ties share a
    rank; low-exposure and unmeasured creatives list separately with
    reasons instead of becoming false winners.
    """
    objective = analysis.get("objective", "reach")
    rank_by = rank_by or DEFAULT_RANK.get(objective, "hook_rate_2s_impr")
    ranked, excluded = [], []
    for creative in analysis.get("creatives", []):
        res = (creative.get("metrics") or {}).get(rank_by)
        exposure = (creative.get("exposure") or {}).get(
            "impressions", 0)
        if not diagnostics._measured(res):
            excluded.append(
                {"creative_key": creative["creative_key"],
                 "reason": "no measured %s" % rank_by})
        elif exposure < diagnostics.MIN_IMPRESSIONS:
            excluded.append(
                {"creative_key": creative["creative_key"],
                 "reason": "low exposure (%d impressions)" % exposure})
        else:
            ranked.append((creative["creative_key"], res["value"],
                           exposure))
    reverse = metrics.METRICS.get(rank_by, {}).get(
        "direction", "higher_is_better") == "higher_is_better"
    ranked.sort(key=lambda t: t[1], reverse=reverse)
    table, last_value, rank = [], None, 0
    for i, (key, value, exposure) in enumerate(ranked):
        if value != last_value:
            rank = i + 1
            last_value = value
        table.append({"rank": rank, "creative_key": key, "value": value,
                      "exposure": exposure})
    definition = dict(metrics.METRICS.get(rank_by, {}))
    return {"rank_by": rank_by, "objective": objective,
            "definition": {"metric_id": rank_by,
                           "display": definition.get("display", {}),
                           "numerator": definition.get("numerator"),
                           "denominator": definition.get("denominator"),
                           "unit": definition.get("unit"),
                           "direction": definition.get("direction"),
                           "aggregation": definition.get("aggregation"),
                           "definition_version":
                           metrics.DEFINITION_VERSION},
            "table": table, "excluded": excluded,
            "winner": table[0] if table else None}


def recommendations_from_findings(analysis, limit=None):
    """One recommendation per finding: preserve / change / evidence /
    outcome. Sorted by finding priority; no promised uplift."""
    recommendations = []
    for creative in analysis.get("creatives", []):
        for finding in creative.get("findings", []):
            recommendations.append({
                "finding_id": finding["finding_id"],
                "creative_ids": list(finding["creative_ids"]),
                "priority": finding["priority"],
                "layer": finding.get("layer", ""),
                "preserve": finding["element_to_preserve"],
                "change": finding["element_to_change"],
                "evidence": {
                    "signal": finding["primary_signal"],
                    "observed": finding["observed_values"],
                    "benchmarks": finding["benchmark_values"],
                    "confidence": finding["confidence_level"],
                    "confidence_reasons":
                        finding["confidence_reasons"],
                    "limitations": finding["limitations"]},
                "iteration": finding["recommended_iteration"],
                "outcome_to_measure":
                    _outcome_for(finding, analysis.get("objective")),
                "recommended_test_id":
                    finding.get("recommended_test_id")})
    order = {"high": 0, "medium": 1, "low": 2, "exploratory": 3}
    recommendations.sort(
        key=lambda r: order.get(r["priority"], 4))
    if limit is not None:
        recommendations = recommendations[:limit]
    return recommendations


def _outcome_for(finding, objective):
    """What the next test must measure (objective-aware)."""
    layer = finding.get("layer", "")
    if objective == "conversions":
        return {"conversions": "primary success metric for this"
                               " conversion brief",
                "guardrails": ["CPA", "spend pacing"]}
    outcomes = {"stop": "2s/3s Hook Rate (same definition)",
                "hold": "hold rate (same numerator/denominator)",
                "depth": "quartile viewing + AWT seconds",
                "brand": "measured brand recall via a study, or"
                         " repeat-observation of brand encounters",
                "efficiency": "CPM/CPCV at comparable spend"}
    return {"attention": outcomes.get(layer, "the finding's metric"),
            "guardrails": ["spend pacing", "frequency"],
            "note": "CTR stays secondary on Reach briefs; do not"
                    " optimize the test around clicks"}


def test_plan_for_finding(finding, analysis, control_key=None):
    """Controlled test plan: one variable changes, rest held constant.

    Never promises an uplift. Reach plans never optimize around
    clicks merely because CTR exists.
    """
    objective = analysis.get("objective", "reach")
    creative_ids = finding.get("creative_ids") or []
    control = control_key or (creative_ids[0] if creative_ids else "")
    layer = finding.get("layer", "")
    primary = {
        "stop": "hook_rate_2s_impr", "hold": "hold_rate",
        "depth": "awt_per_view", "brand": "quartile_50_impr",
        "efficiency": "cpcv" if objective == "reach" else "cpa"}.get(
            layer, "hook_rate_2s_impr")
    if objective == "conversions" and layer in ("stop", "hold",
                                                "depth"):
        secondary = ["cpa", "cvr", "spend pacing"]
    elif objective == "reach":
        secondary = ["frequency", "spend pacing",
                     "ctr_link (secondary only)"]
    else:
        secondary = ["cpa", "spend pacing"]
    return {
        "test_id": "test_%s" % finding["finding_id"],
        "finding_id": finding["finding_id"],
        "hypothesis": finding["creative_hypothesis"],
        "control_creative": control,
        "proposed_variant": finding["recommended_iteration"],
        "primary_variable_changed": finding["element_to_change"],
        "elements_held_constant": [finding["element_to_preserve"],
                                   "audience, placement, budget split,"
                                   " flight dates"],
        "campaign_objective": objective,
        "primary_success_metric": primary,
        "secondary_metrics": secondary,
        "guardrails": secondary[-1:] + ["frequency"],
        "comparison_conditions": {
            "scope": analysis.get("scope"),
            "dataset_version": analysis.get("dataset_version"),
            "metric_definitions": finding.get(
                "metric_definition_ids", []),
            "note": "same scope, same definitions, same window length"},
        "evaluation_plan": "compare %s between control and variant at"
                           " matched spend; require the same metric"
                           " definition on both arms" % primary,
        "limitations": list(finding.get("limitations", [])) + [
            "no uplift promised; a null result is a learning"]}

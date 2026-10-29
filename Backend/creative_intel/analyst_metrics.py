"""Foap Analyst metric registry + deterministic calculation engine.

Every performance number the analyst shows comes from here — never
from the LLM. The registry fixes each metric's definition
(numerator, denominator, unit, direction, valid grain, aggregation
rules); the engine computes pooled/mean/median aggregates with
explicit data states.

Data states (spec section 5): MEASURED, MISSING, UNSUPPORTED,
ESTIMATED, NA. A stored 0 for a field listed in the row's
missing_json means "not supplied", never a measured zero. Rows
imported before missing-data tracking predate it and read as
measured zeros (documented limitation, surfaced in methodology).
"""

from __future__ import annotations

import math

from .currency_scope import money_scope
from .metric_availability import missing_fields as _missing_of

DEFINITION_VERSION = "analyst-metrics-v1"

MEASURED = "measured"
MISSING = "missing"
UNSUPPORTED = "unsupported"
ESTIMATED = "estimated"
NA = "not_applicable"

# Fields whose values must never be summed across rows (per-person /
# per-exposure semantics differ per row; TikTok documents reach,
# frequency and per-person watch time as non-additive).
NON_ADDITIVE = {"reach", "frequency", "avg_watch_per_user_s"}

# Numeric fields the engine may pool by summation.
SUMMABLE = {"spend", "impressions", "clicks", "link_clicks",
            "conversions", "video_views", "video_starts", "views_2s",
            "views_3s", "views_6s", "views_25", "views_50",
            "views_75", "views_100", "watch_time_total_s", "likes",
            "comments", "shares", "saves", "revenue"}

METRICS = {
    "hook_rate_2s_impr": {
        "display": {"en": "2s Hook Rate (impressions-based)",
                     "pl": "Hook Rate 2 s (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_2s",
        "numerator": "views_2s",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_2s", "impressions"),
    },
    "hook_rate_3s_impr": {
        "display": {"en": "3s Hook Rate (impressions-based)",
                     "pl": "Hook Rate 3 s (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_3s",
        "numerator": "views_3s",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_3s", "impressions"),
    },
    "hold_rate": {
        "display": {"en": "Hold Rate (defined numerator/denominator)",
                     "pl": "Hold Rate (zdefiniowany licznik/mianownik)"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "configured",
        "denominator": "configured",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("configured",),
    },
    "vtr": {
        "display": {"en": "View-Through Rate (completions ÷ impressions)",
                     "pl": "VTR (ukończenia ÷ wyświetlenia)"},
        "source_platform": "any",
        "native_field": "views_100",
        "numerator": "views_100",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_100", "impressions"),
    },
    # A15: the plays-based rate ordinary analytics used to publish
    # under the "vtr" id. Separate id, explicit label, same shared
    # registry — the two rates can never be confused again.
    "view_rate": {
        "display": {"en": "Play/view rate (plays ÷ impressions)",
                     "pl": "Wskaźnik odtworzeń (odtworzenia ÷ wyświetlenia)"},
        "source_platform": "any",
        "native_field": "video_views",
        "numerator": "video_views",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("video_views", "impressions"),
    },
    "quartile_25_impr": {
        "display": {"en": "25% viewing rate (impressions-based)",
                     "pl": "Oglądalność 25% (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_25",
        "numerator": "views_25",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_25", "impressions"),
    },
    "quartile_50_impr": {
        "display": {"en": "50% viewing rate (impressions-based)",
                     "pl": "Oglądalność 50% (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_50",
        "numerator": "views_50",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_50", "impressions"),
    },
    "quartile_75_impr": {
        "display": {"en": "75% viewing rate (impressions-based)",
                     "pl": "Oglądalność 75% (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_75",
        "numerator": "views_75",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_75", "impressions"),
    },
    "completion_impr": {
        "display": {"en": "Completion rate (impressions-based)",
                     "pl": "Wskaźnik ukończeń (na bazie wyświetleń)"},
        "source_platform": "any",
        "native_field": "views_100",
        "numerator": "views_100",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_100", "impressions"),
    },
    "quartile_25_starts": {
        "display": {"en": "25% viewing rate (video-starts-based)",
                     "pl": "Oglądalność 25% (na bazie startów)"},
        "source_platform": "tiktok",
        "native_field": "views_25",
        "numerator": "views_25",
        "denominator": "video_starts",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("views_25", "video_starts"),
    },
    "awt_per_view": {
        "display": {"en": "Average watch time per view",
                     "pl": "Średni czas oglądania na odtworzenie"},
        "source_platform": "any",
        "native_field": "watch_time_total_s",
        "numerator": "watch_time_total_s",
        "denominator": "matching view count",
        "unit": "seconds",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "totals_over_matching_count",
        "requires": ("watch_time_total_s",),
    },
    "awt_per_user": {
        "display": {"en": "Average watch time per user",
                     "pl": "Średni czas oglądania na użytkownika"},
        "source_platform": "tiktok",
        "native_field": "avg_watch_per_user_s",
        "numerator": "avg_watch_per_user_s",
        "denominator": "per-user basis",
        "unit": "seconds",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "never_pooled",
        "requires": ("avg_watch_per_user_s",),
    },
    "awt_pct_duration": {
        "display": {"en": "AWT as % of creative duration",
                     "pl": "AWT jako % długości kreacji"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "awt_per_view",
        "denominator": "creative duration_s",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "per_creative_only",
        "requires": ("watch_time_total_s", "duration_s"),
    },
    "cpm": {
        "display": {"en": "CPM", "pl": "CPM"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "spend",
        "denominator": "impressions",
        "unit": "currency_per_mille",
        "direction": "lower_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("spend", "impressions"),
    },
    "cost_per_1000_reached": {
        "display": {"en": "Cost per 1,000 reached",
                     "pl": "Koszt na 1000 zasięgu"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "spend",
        "denominator": "reach",
        "unit": "currency_per_mille",
        "direction": "lower_is_better",
        "grain": "creative",
        "aggregation": "single_scope_only",
        "requires": ("spend", "reach"),
    },
    "cpcv": {
        "display": {"en": "CPCV (completed views)",
                     "pl": "CPCV (ukończone odtworzenia)"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "spend",
        "denominator": "views_100",
        "unit": "currency",
        "direction": "lower_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("spend", "views_100"),
    },
    "reach": {
        "display": {"en": "Reported unique reach (scope-level)",
                     "pl": "Raportowany zasięg (poziom zakresu)"},
        "source_platform": "any",
        "native_field": "reach",
        "numerator": "reach",
        "denominator": "scope audience",
        "unit": "count",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "never_pooled",
        "requires": ("reach",),
    },
    "engagement_rate": {
        "display": {"en": "Engagement rate (interactions ÷ impressions)",
                     "pl": "Wskaźnik zaangażowania"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "likes+comments+shares+saves",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("likes", "comments", "shares", "saves",
                     "impressions"),
    },
    "frequency": {
        "display": {"en": "Frequency", "pl": "Częstotliwość"},
        "source_platform": "any",
        "native_field": "frequency",
        "numerator": "impressions",
        "denominator": "reach",
        "unit": "ratio",
        "direction": "neutral",
        "grain": "creative",
        "aggregation": "reported_or_single_scope",
        "requires": ("frequency", "impressions", "reach"),
    },
    "ctr_link": {
        "display": {"en": "CTR (destination/link clicks)",
                     "pl": "CTR (kliknięcia w link)"},
        "source_platform": "any",
        "native_field": "link_clicks",
        "numerator": "link_clicks",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("link_clicks", "impressions"),
    },
    "ctr_all": {
        "display": {"en": "CTR (all clicks)",
                     "pl": "CTR (wszystkie kliknięcia)"},
        "source_platform": "any",
        "native_field": "clicks",
        "numerator": "clicks",
        "denominator": "impressions",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("clicks", "impressions"),
    },
    "cvr": {
        "display": {"en": "CVR (conversion event as supplied)",
                     "pl": "CVR (zdarzenie konwersji)"},
        "source_platform": "any",
        "native_field": "conversions",
        "numerator": "conversions",
        "denominator": "link_clicks",
        "unit": "percent",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("conversions", "link_clicks"),
    },
    "cpa": {
        "display": {"en": "CPA (conversion event as supplied)",
                     "pl": "CPA (zdarzenie konwersji)"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "spend",
        "denominator": "conversions",
        "unit": "currency",
        "direction": "lower_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("spend", "conversions"),
    },
    "roas": {
        "display": {"en": "ROAS (reported revenue only)",
                     "pl": "ROAS (tylko raportowany przychód)"},
        "source_platform": "any",
        "native_field": None,
        "numerator": "revenue",
        "denominator": "spend",
        "unit": "ratio",
        "direction": "higher_is_better",
        "grain": "creative",
        "aggregation": "pooled_ratio",
        "requires": ("revenue", "spend"),
    },
}


def field_state(rows, field):
    """Availability of one raw field across rows.

    Returns (state, usable_rows): UNSUPPORTED when no row carries the
    field (every row lists it missing); MISSING when some rows do;
    MEASURED otherwise. A stored 0 for a non-missing field is a
    measured zero, never converted.
    """
    if not rows:
        return UNSUPPORTED, []
    usable = [r for r in rows if field not in _missing_of(r)]
    if not usable:
        return UNSUPPORTED, []
    if len(usable) < len(rows):
        return MISSING, usable
    return MEASURED, usable


def _num(row, field):
    try:
        value = float(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _result(metric_id, value, state, basis="", reasons=None,
            numerator=0.0, denominator=0.0):
    return {"metric_id": metric_id,
            "definition_version": DEFINITION_VERSION,
            "value": value,
            "state": state,
            "basis": basis,
            "reasons": list(reasons or []),
            "numerator": numerator,
            "denominator": denominator,
            "unit": METRICS[metric_id]["unit"],
            "direction": METRICS[metric_id]["direction"]}


def _currencies(rows):
    scope = money_scope(rows)
    currencies = scope["currencies"]
    if currencies and scope["unknown_currency_contribution"]:
        return currencies + ["(unknown)"]
    return currencies


def _currency_ok(rows):
    """Single-currency (or currency-free) scope check.

    Cost metrics pool spend only when every row shares one currency
    or none is recorded. Mixed currencies without a conversion policy
    are never combined.
    """
    return not money_scope(rows)["mixed_currency"]


def unavailable_mixed_currency(metric_id, rows):
    """NA result for money metrics over multi-currency scopes (A14).

    No FX conversion exists anywhere in the app, so a blended money
    number is never produced — callers surface this NA instead.
    """
    return _result(metric_id, None, NA,
                   reasons=["mixed currencies %s need a conversion policy"
                            % _currencies(rows)])


def pooled_ratio(rows, metric_id, num_field, den_field, scale=100.0):
    """Compatible numerators/denominators summed first, then divided.

    Never averages per-row percentages. Zero denominator yields NA
    (not zero); every input row missing a side yields UNSUPPORTED.
    """
    if metric_id not in METRICS:
        raise ValueError("unknown metric %r" % (metric_id,))
    num_supplied = den_supplied = 0
    usable = []
    for row in rows:
        missing = _missing_of(row)
        has_num = num_field not in missing
        has_den = den_field not in missing
        num_supplied += has_num
        den_supplied += has_den
        if has_num and has_den:
            usable.append(row)
    if not num_supplied or not den_supplied:
        return _result(metric_id, None, UNSUPPORTED,
                       reasons=["%s or %s not supplied in scope"
                                % (num_field, den_field)])
    # Preserve input order, duplicate rows and Python's float summation.
    num = sum(_num(r, num_field) for r in usable)
    den = sum(_num(r, den_field) for r in usable)
    reasons = []
    if num_supplied < len(rows) or den_supplied < len(rows):
        reasons.append("%d of %d rows lack %s/%s; pooled from %d rows"
                       % (len(rows) - len(usable), len(rows),
                          num_field, den_field, len(usable)))
    if den <= 0:
        return _result(metric_id, None, NA, numerator=num,
                       denominator=den,
                       reasons=reasons + ["denominator is zero"])
    state = ESTIMATED if reasons else MEASURED
    return _result(metric_id, num / den * scale, state, basis="pooled",
                   reasons=reasons, numerator=num, denominator=den)


def _per_creative_values(rows, metric_id, num_field, den_field, scale=100.0):
    """Per-creative pooled ratios for mean/median aggregation.

    Rows collapse to independent creative units first, so ten daily
    rows from one creative count once.
    """
    by_creative = {}
    for row in rows:
        by_creative.setdefault(row.get("creative_key") or "", []).append(row)
    values = []
    for key, grows in by_creative.items():
        res = pooled_ratio(grows, metric_id, num_field, den_field,
                           scale=scale)
        if res["state"] in (MEASURED, ESTIMATED) and res["value"] is not None:
            values.append((key, res["value"]))
    return values


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mean_of_rates(rows, metric_id, num_field, den_field, scale=100.0):
    """Unweighted mean of creative-level rates, explicitly labelled."""
    values = _per_creative_values(rows, metric_id, num_field, den_field,
                                  scale=scale)
    if not values:
        return _result(metric_id, None, NA,
                       reasons=["no creative with a computable rate"])
    mean = sum(v for _, v in values) / len(values)
    return _result(metric_id, mean, ESTIMATED,
                   basis="mean_of_%d_creative_rates" % len(values),
                   reasons=["unweighted mean of creative rates; use the"
                            " pooled rate for totals"])


def median_of_rates(rows, metric_id, num_field, den_field, scale=100.0):
    """Median of creative-level rates, explicitly labelled."""
    values = _per_creative_values(rows, metric_id, num_field, den_field,
                                  scale=scale)
    if not values:
        return _result(metric_id, None, NA,
                       reasons=["no creative with a computable rate"])
    return _result(metric_id, _median([v for _, v in values]), ESTIMATED,
                   basis="median_of_%d_creative_rates" % len(values),
                   reasons=["median of creative rates; use the pooled"
                            " rate for totals"])


def hook_rate_2s(rows):
    """Impressions-based 2s Hook Rate; never substitutes other views."""
    return pooled_ratio(rows, "hook_rate_2s_impr", "views_2s",
                        "impressions")


def hook_rate_3s(rows):
    """Impressions-based 3s Hook Rate from actual 3s views only."""
    return pooled_ratio(rows, "hook_rate_3s_impr", "views_3s",
                        "impressions")


def hold_rate(rows, num_field, den_field):
    """Later-stage/earlier-stage hold with named compatible fields.

    Compatibility (populations and thresholds) is the caller's
    responsibility: pass the explicitly selected numerator and
    denominator fields; both are recorded on the result so a 25%-of-6s
    numerator can never silently pose as post-3s retention.
    """
    res = pooled_ratio(rows, "hold_rate", num_field, den_field)
    res["numerator_field"] = num_field
    res["denominator_field"] = den_field
    return res


def _watch_bases(rows):
    return sorted({(r.get("watch_time_basis") or "") for r in rows
                   if _num(r, "watch_time_total_s") >= 0})


def awt_per_view(rows, durations=None):
    """Average watch time per view: totals over the matching count.

    Prefers summed watch_time_total_s over summed matching view
    counts. Falls back to a view-weighted mean of reported per-view
    averages only when totals are absent but weights exist; per-user
    averages are never mixed in. Returns (awt_result, pct_result).
    """
    _, total_rows = field_state(rows, "watch_time_total_s")
    totals = [(r, _num(r, "watch_time_total_s")) for r in total_rows]
    totals = [(r, v) for r, v in totals if v >= 0]
    if totals:
        # A supplied zero is a measurement. Include it with its matching
        # positive count, and exclude incomplete rows from both sums.
        matched = []
        for row, value in totals:
            count_field = ("video_starts" if row.get("watch_time_basis") == "starts"
                           else "video_views")
            count = _num(row, count_field)
            if count_field not in _missing_of(row) and count > 0:
                matched.append((row, value, count))
        if not matched:
            none = _result("awt_per_view", None, NA,
                           reasons=["no positive matching view counts for supplied totals"])
            return none, _result("awt_pct_duration", None, NA,
                                 reasons=["no positive matching view counts"])
        bases = _watch_bases([row for row, _, _ in matched])
        if len(bases) > 1:
            none = _result("awt_per_view", None, NA,
                           reasons=["mixed watch-time bases %s cannot pool" % bases])
            return none, _result("awt_pct_duration", None, NA,
                                 reasons=["mixed watch-time bases %s cannot pool" % bases])
        count_field = ("video_starts" if (bases and bases[0] == "starts")
                       else "video_views")
        num = sum(value for _, value, _ in matched)
        den = sum(count for _, _, count in matched)
        reasons = []
        if len(matched) < len(rows):
            reasons.append(
                "pooled from %d of %d rows; rows without supplied watch time"
                " or a positive matching %s are excluded from both sums"
                % (len(matched), len(rows), count_field))
        awt = _result("awt_per_view", num / den, MEASURED,
                      basis="total_over_%s" % count_field,
                      numerator=num, denominator=den, reasons=reasons)
    elif total_rows:
        none = _result("awt_per_view", None, NA,
                       reasons=["supplied watch totals contain no nonnegative values"])
        return none, _result("awt_pct_duration", None, NA,
                             reasons=["supplied watch totals contain no nonnegative values"])
    else:
        # Weighted mean of reported per-view averages with correct
        # weights; rounded source averages make this an approximation.
        _, average_rows = field_state(rows, "avg_watch_per_view_s")
        if not average_rows:
            reason = "no watch totals or reported per-view averages supplied"
            return (_result("awt_per_view", None, UNSUPPORTED, reasons=[reason]),
                    _result("awt_pct_duration", None, UNSUPPORTED, reasons=[reason]))
        weighted, weights = 0.0, 0.0
        matched_count = 0
        for r in average_rows:
            avg = _num(r, "avg_watch_per_view_s")
            w = _num(r, "video_views")
            if avg >= 0 and w > 0 and "video_views" not in _missing_of(r):
                weighted += avg * w
                weights += w
                matched_count += 1
        if weights <= 0:
            none = _result("awt_per_view", None, NA,
                           reasons=["totals and weighted averages both"
                                    " unavailable"])
            return none, _result("awt_pct_duration", None, NA,
                                 reasons=["totals and weighted averages"
                                          " both unavailable"])
        reasons = ["approximation from rounded source averages"]
        if matched_count < len(rows):
            reasons.append(
                "pooled from %d of %d rows; rows without a supplied nonnegative"
                " per-view average or positive video_views are excluded from both sums"
                % (matched_count, len(rows)))
        awt = _result("awt_per_view", weighted / weights, ESTIMATED,
                      basis="weighted_mean_of_reported_avgs",
                      numerator=weighted, denominator=weights,
                      reasons=reasons)
    pct = _result("awt_pct_duration", None, NA,
                  reasons=["needs a single creative duration"])
    if durations is not None and len({r.get("creative_key") for r in rows
                                      }) == 1 and awt["value"] is not None:
        key = rows[0].get("creative_key") or ""
        duration = float((durations or {}).get(key) or 0)
        if duration > 0:
            pct = _result("awt_pct_duration",
                          awt["value"] / duration * 100.0, awt["state"],
                          basis="own_duration_%ss" % duration,
                          reasons=list(awt["reasons"]))
    return awt, pct


def cpm(rows):
    """Spend over impressions; mixed currencies never combine."""
    if not _currency_ok(rows):
        return _result("cpm", None, NA,
                       reasons=["mixed currencies %s need a conversion"
                                " policy" % _currencies(rows)])
    res = pooled_ratio(rows, "cpm", "spend", "impressions", scale=1000.0)
    currencies = _currencies(rows)
    if currencies:
        res["reasons"] = list(res["reasons"])
        res["basis"] = (res["basis"] + " in %s" % currencies[0]).strip()
    return res


def cost_per_1000_reached(rows):
    """Spend over valid unique reach for the same scope only.

    Reach is never summed across overlapping rows: multi-row scopes
    return unavailable unless a single row carries the scope reach.
    """
    state, usable = field_state(rows, "reach")
    if state == UNSUPPORTED:
        return _result("cost_per_1000_reached", None, UNSUPPORTED,
                       reasons=["no unique reach supplied in scope"])
    if len(usable) > 1:
        return _result("cost_per_1000_reached", None, NA,
                       reasons=["reach cannot be summed across %d rows;"
                                " supply scope-level reach or narrow to one"
                                " creative/day" % len(usable)])
    row = usable[0]
    reach = _num(row, "reach")
    if reach <= 0:
        return _result("cost_per_1000_reached", None, NA,
                       reasons=["scope reach is zero"])
    spend_state, _ = field_state([row], "spend")
    if spend_state == UNSUPPORTED:
        return _result("cost_per_1000_reached", None, UNSUPPORTED,
                       reasons=["no spend supplied for the row with unique reach"])
    spend = _num(row, "spend")
    if not _currency_ok(rows):
        return _result("cost_per_1000_reached", None, NA,
                       reasons=["mixed currencies %s need a conversion"
                                " policy" % _currencies(rows)])
    return _result("cost_per_1000_reached", spend / reach * 1000.0,
                   MEASURED, basis="single_scope_reach",
                   numerator=spend, denominator=reach)


def frequency(rows):
    """Reported frequency, or supplied impressions/reach on one observed row."""
    _, usable = field_state(rows, "frequency")
    reported = [(r, _num(r, "frequency")) for r in usable
                if _num(r, "frequency") > 0]
    if reported:
        # Reach-weighting recovers the pooled ratio: sum(f*reach) /
        # sum(reach) == sum(impressions) / sum(reach). Impression
        # weights would over-weight high-frequency rows instead.
        rrows = [(r, v) for r, v in reported
                 if "reach" not in _missing_of(r)
                 and _num(r, "reach") > 0]
        if rrows:
            reasons = ["reach-weighted mean of reported frequency"]
            if len(rrows) < len(reported):
                reasons.append(
                    "%d of %d rows lack reach and are excluded"
                    % (len(reported) - len(rrows), len(reported)))
            weights = sum(_num(r, "reach") for r, _ in rrows)
            value = sum(v * _num(r, "reach") for r, v in rrows) / weights
            return _result("frequency", value, ESTIMATED,
                           basis="reach_weighted_reported",
                           reasons=reasons)
        value = sum(v for _, v in reported) / len(reported)
        return _result("frequency", value, ESTIMATED,
                       basis="mean_reported",
                       reasons=["mean of reported frequency"])
    if len(rows) == 1 and not {"impressions", "reach"}.intersection(_missing_of(rows[0])):
        reach = _num(rows[0], "reach")
        impr = _num(rows[0], "impressions")
        if reach > 0:
            return _result("frequency", impr / reach, MEASURED,
                           basis="impressions_over_scope_reach",
                           numerator=impr, denominator=reach)
    return _result("frequency", None, NA,
                   reasons=["no reported frequency; fallback requires one row"
                            " with supplied impressions and positive reach"])


def engagement_rate(rows):
    """Pooled interactions over impressions, per platform definition.

    Numerator and denominator use the same rows: supplied impressions
    and at least one interaction field. Partial interaction families are
    retained as estimates, counting only the supplied interaction fields.
    """
    fields = ("likes", "comments", "shares", "saves")
    prepared = [(row, _missing_of(row)) for row in rows]
    have_interactions = [(row, missing) for row, missing in prepared
                         if any(field not in missing for field in fields)]
    if not have_interactions:
        return _result("engagement_rate", None, UNSUPPORTED,
                       reasons=["no interaction fields supplied"])
    usable = [(row, missing) for row, missing in have_interactions
              if "impressions" not in missing]
    if not usable:
        return _result("engagement_rate", None, UNSUPPORTED,
                       reasons=["no rows supply both impressions and interaction fields"])
    num = sum(_num(row, field) for row, missing in usable
              for field in fields if field not in missing)
    den = sum(_num(row, "impressions") for row, _ in usable)
    reasons = []
    if len(usable) < len(prepared):
        reasons.append(
            "%d of %d rows supply impressions and interaction fields;"
            " remaining rows excluded" % (len(usable), len(prepared)))
    partial = sum(any(field in missing for field in fields) for _, missing in usable)
    if partial:
        reasons.append(
            "%d of %d matched rows omit some interaction fields;"
            " only supplied interactions counted" % (partial, len(usable)))
    if den <= 0:
        return _result("engagement_rate", None, NA, numerator=num, denominator=den,
                       reasons=reasons + ["no positive reported impressions in matched rows"])
    state = ESTIMATED if reasons else MEASURED
    return _result("engagement_rate", num / den * 100.0, state,
                   basis="pooled_interactions", numerator=num,
                   denominator=den, reasons=reasons)


def cpcv(rows):
    """Spend over compatible completed views (views_100)."""
    if not _currency_ok(rows):
        return unavailable_mixed_currency("cpcv", rows)
    return pooled_ratio(rows, "cpcv", "spend", "views_100", scale=1.0)


def compare_groups(rows, group_key, metric_id, num_field, den_field,
                   scale=100.0, min_exposure_field="impressions"):
    """Traceable group comparison over independent creative units.

    Returns per-group pooled metric, creative ids, row counts and
    exposure. Callers label exploratory limits (small n, confounding);
    this function never calls a difference a correlation.
    """
    groups = {}
    for row in rows:
        groups.setdefault(row.get(group_key) or "unknown", []).append(row)
    out = {}
    for name, grows in sorted(groups.items()):
        creative_ids = sorted({g.get("creative_key") or ""
                               for g in grows} - {""})
        exposure = sum(_num(g, min_exposure_field) for g in grows)
        metric = pooled_ratio(grows, metric_id, num_field, den_field,
                              scale=scale)
        out[name] = {"metric": metric,
                     "creative_ids": creative_ids,
                     "creative_count": len(creative_ids),
                     "row_count": len(grows),
                     "exposure": exposure}
    return out

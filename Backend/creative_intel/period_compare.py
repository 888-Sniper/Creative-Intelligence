"""Previous-equivalent-period KPI comparisons over real aggregates.

Convention (shared with the frontend): date ranges are INCLUSIVE on
both ends. The previous equivalent of [start, end] is the equally
long range ending the day before start:

    days = (end - start).days + 1
    prev_end = start - 1 day
    prev_start = prev_end - (days - 1) days

Jan 1 – Mar 31, 2024 (91 days) therefore compares against
Oct 2 – Dec 31, 2023.

Ratios (CTR/CPA/CPM/ROAS/Play Rate) are recomputed per period from
pooled raw sums via benchmarks.kpis_for_rows — never by averaging
already-computed ratios.
"""

import datetime

from . import benchmarks

# metric -> "higher" (up is good) | "lower" (down is good) | "neutral".
SENTIMENT = {
    "spend": "neutral",
    "impressions": "higher",
    "clicks": "higher",
    "conversions": "higher",
    "video_views": "higher",
    "revenue": "higher",
    "ctr": "higher",
    "cpc": "lower",
    "cpm": "lower",
    "cpa": "lower",
    "vtr": "higher",
    "view_rate": "higher",
    "roas": "higher",
}

COMPARED_METRICS = tuple(SENTIMENT)


def previous_period(date_from, date_to):
    """Equal-length range immediately before [date_from, date_to].

    Both bounds are YYYY-MM-DD strings; both ranges are inclusive.
    Raises ValueError on bad input or an inverted range.
    """
    start = benchmarks._iso_day(date_from, "date_from")
    end = benchmarks._iso_day(date_to, "date_to")
    lo = datetime.date.fromisoformat(start)
    hi = datetime.date.fromisoformat(end)
    if lo > hi:
        raise ValueError("date_from %r is after date_to %r" % (start, end))
    days = (hi - lo).days + 1
    prev_end = lo - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=days - 1)
    return prev_start.isoformat(), prev_end.isoformat()


def _raw_sums(rows):
    """Pooled raw components both periods share (ratios derive from these)."""
    return {
        "n_ads": len(rows),
        "spend": sum(r.get("spend", 0) or 0 for r in rows),
        "impressions": sum(r.get("impressions", 0) or 0 for r in rows),
        "clicks": sum(r.get("clicks", 0) or 0 for r in rows),
        "conversions": sum(r.get("conversions", 0) or 0 for r in rows),
        "video_views": sum(r.get("video_views", 0) or 0 for r in rows),
        "revenue": sum(r.get("revenue", 0) or 0 for r in rows),
    }


MONEY_METRICS = frozenset({"spend", "revenue", "cpc", "cpm", "cpa", "roas"})


def _metric_value(sums, pooled, metric):
    """One metric from pooled raw sums (None when not measurable).

    pooled is benchmarks.kpis_for_rows(rows), so currency gating and
    null semantics match the rest of the product.
    """
    if metric == "spend":
        return round(sums["spend"], 2)
    if metric == "impressions":
        return sums["impressions"]
    if metric == "clicks":
        return sums["clicks"]
    if metric == "conversions":
        return sums["conversions"]
    if metric == "video_views":
        return sums["video_views"]
    if metric == "revenue":
        return round(sums["revenue"], 2)
    return pooled.get(metric)


def _money_comparable(cur_pooled, prev_pooled):
    """Money metrics compare only within one currency.

    A USD total against a GBP total (or any mixed-currency side) has
    no honest percentage; callers must treat those metrics as missing.
    """
    if cur_pooled.get("mixed_currency") or prev_pooled.get("mixed_currency"):
        return False
    return cur_pooled.get("currency") == prev_pooled.get("currency")


def _compare_values(current, previous, prev_has_rows=False):
    """(state, percent_change, direction) with honest zero handling.

    state is "compared" | "new" | "none":
      compared — both values measurable, percentage is valid;
      new      — prior window has rows but the metric did not exist
                 there (zero denominator), while it does now;
      none     — nothing to compare (missing data, both zero, or the
                 current value itself is unmeasurable).
    """
    if previous is None:
        if current is None or not prev_has_rows:
            return "none", None, "flat"
        return "new", None, "up"
    if current is None:
        return "none", None, "flat"
    if previous == 0:
        if current == 0:
            return "none", None, "flat"
        return "new", None, "up"
    pct = round((current - previous) / previous * 100, 1)
    if current > previous:
        direction = "up"
    elif current < previous:
        direction = "down"
    else:
        direction = "flat"
    return "compared", pct, direction


def _sentiment(metric, direction):
    if direction == "flat":
        return "neutral"
    kind = SENTIMENT[metric]
    if kind == "neutral":
        return "neutral"
    good_up = kind == "higher"
    is_up = direction == "up"
    return "good" if is_up == good_up else "bad"


def compare_metric(current, previous, metric, prev_has_rows=False):
    """Compare one metric value pair into the API comparison shape."""
    state, pct, direction = _compare_values(current, previous, prev_has_rows)
    out = {
        "current": current,
        "previous": previous,
        "percent_change": pct,
        "direction": direction,
        "sentiment": _sentiment(metric, direction) if state == "compared" else "neutral",
        "state": state,
    }
    if current is not None and previous is not None:
        out["abs_change"] = round(current - previous, 4)
    else:
        out["abs_change"] = None
    return out


def resolve_current_range(conn, filt):
    """Current period from explicit dates, else the dataset extent.

    Returns (start, end) or None when only one bound is set (not a
    real range) or when no dated rows exist in scope.
    """
    lo = (
        (filt.get("date_from") or [None])[0]
        if isinstance(filt.get("date_from"), list)
        else filt.get("date_from")
    )
    hi = (filt.get("date_to") or [None])[0] if isinstance(filt.get("date_to"), list) else filt.get("date_to")
    if lo and hi:
        return lo, hi
    if lo or hi:
        return None
    days = sorted({str(r.get("date") or "") for r in benchmarks.all_rows(conn) if str(r.get("date") or "")})
    if not days:
        return None
    return days[0], days[-1]


def _in_window(rows, filt, start, end):
    window = dict(filt)
    window["date_from"] = start
    window["date_to"] = end
    return [r for r in rows if benchmarks.match_filters(r, window)]


def compare_kpis(conn, scope):
    """Current vs previous-equivalent KPI comparison for one scope.

    scope is a normalized filter dict (benchmarks.Scope.normalized()):
    every non-date axis applies identically to both windows; only the
    date range differs. Returns the API payload with ISO period
    bounds and per-metric comparisons, or {"comparison": None, ...}
    when no real range can be resolved.
    """
    filt = benchmarks.normalize_filters(dict(scope or {}))
    # Exact `date` days with no date_from/date_to pair define the
    # current period (one day, or min..max for several); the days must
    # not also constrain the previous window. With an explicit range,
    # `date` stays an ordinary row filter for both windows (matching
    # /api/campaigns semantics).
    exact_days = sorted(set(filt.get("date") or []))
    use_exact = bool(exact_days) and not (filt.get("date_from") and filt.get("date_to"))
    base = {
        k: v for k, v in filt.items() if k not in ("date_from", "date_to") and (not use_exact or k != "date")
    }
    if use_exact:
        current = (exact_days[0], exact_days[-1])
    else:
        current = resolve_current_range(conn, filt)
    if current is None:
        return {"current_period": None, "previous_period": None, "comparison": None, "metrics": {}}
    cur_start, cur_end = current
    prev_start, prev_end = previous_period(cur_start, cur_end)
    rows = benchmarks.all_rows(conn)
    cur_rows = _in_window(rows, base, cur_start, cur_end)
    prev_rows = _in_window(rows, base, prev_start, prev_end)
    if not cur_rows and not prev_rows:
        # Explicitly empty selection (e.g. a status/spend band nothing
        # satisfies): report no comparison rather than dataset-extent
        # periods with null metrics.
        return {"current_period": None, "previous_period": None,
                "comparison": None, "metrics": {}}
    cur_sums, prev_sums = _raw_sums(cur_rows), _raw_sums(prev_rows)
    cur_pooled = benchmarks.kpis_for_rows(cur_rows)
    prev_pooled = benchmarks.kpis_for_rows(prev_rows)
    money_ok = _money_comparable(cur_pooled, prev_pooled)
    metrics = {}
    for metric in COMPARED_METRICS:
        if not cur_rows and not prev_rows:
            cur_val, prev_val = None, None
        elif not cur_rows:
            cur_val, prev_val = None, _metric_value(prev_sums, prev_pooled, metric)
        elif not prev_rows:
            cur_val, prev_val = _metric_value(cur_sums, cur_pooled, metric), None
        else:
            cur_val = _metric_value(cur_sums, cur_pooled, metric)
            prev_val = _metric_value(prev_sums, prev_pooled, metric)
        if metric in MONEY_METRICS and not money_ok:
            cur_val, prev_val = None, None
        metrics[metric] = compare_metric(cur_val, prev_val, metric, prev_has_rows=bool(prev_rows))
    return {
        "current_period": {"start": cur_start, "end": cur_end},
        "previous_period": {"start": prev_start, "end": prev_end},
        "comparison": "previous_period",
        "metrics": metrics,
    }

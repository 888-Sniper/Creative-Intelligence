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

from . import benchmarks, period_metrics
from .metric_availability import reported_raw_totals as _raw_sums

# Retain the existing helper entry points while isolating pure arithmetic.
SENTIMENT = period_metrics.SENTIMENT
COMPARED_METRICS = period_metrics.COMPARED_METRICS
MONEY_METRICS = period_metrics.MONEY_METRICS
_compare_values = period_metrics._compare_values
_metric_value = period_metrics._metric_value
_money_comparable = period_metrics._money_comparable
_sentiment = period_metrics._sentiment
compare_metric = period_metrics.compare_metric


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
        return {"current_period": None, "previous_period": None, "comparison": None, "metrics": {},
                "current_n_ads": 0, "previous_n_ads": 0,
                "currency_context": period_metrics.period_currency_context({}, {})}
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
                "comparison": None, "metrics": {},
                "current_n_ads": 0, "previous_n_ads": 0,
                "currency_context": period_metrics.period_currency_context({}, {})}
    cur_sums, prev_sums = _raw_sums(cur_rows), _raw_sums(prev_rows)
    cur_pooled = benchmarks.kpis_for_rows(cur_rows)
    prev_pooled = benchmarks.kpis_for_rows(prev_rows)
    metrics = period_metrics.compare_period_metrics(cur_sums, prev_sums, cur_pooled, prev_pooled)
    return {
        "current_period": {"start": cur_start, "end": cur_end},
        "previous_period": {"start": prev_start, "end": prev_end},
        "comparison": "previous_period",
        "metrics": metrics,
        "current_n_ads": len(cur_rows),
        "previous_n_ads": len(prev_rows),
        "currency_context": period_metrics.period_currency_context(cur_pooled, prev_pooled),
    }

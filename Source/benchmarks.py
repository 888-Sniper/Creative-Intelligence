"""Benchmark engine (Schema v0 rules).

- Spend-weighted means; never average-of-ratios.
- p25 / median / p75 bands per cohort.
- Min-n guard: fewer than 5 creatives or 3 projects -> insufficient-data
  status plus a pooled fallback when one is supplied.
"""

MIN_CREATIVES = 5
MIN_PROJECTS = 3


def spend_weighted_mean(values, weights):
    """Spend-weighted mean. None when no positive weight remains.

    Missing values are left out. A genuine zero with positive weight
    stays zero. An empty or zero-weight pool is unavailable, not 0.
    """
    pairs = [(v, w) for v, w in zip(values, weights)
             if v is not None and w is not None]
    total = sum(w for _v, w in pairs)
    if total <= 0:
        return None
    return sum(v * w for v, w in pairs) / total


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = pct / 100 * (len(sorted_vals) - 1)
    low = int(rank)
    frac = rank - low
    high = min(low + 1, len(sorted_vals) - 1)
    return sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * frac


def describe(values, weights):
    # None is unavailable, not a measured zero, so it stays out of the band.
    ordered = sorted(value for value in values if value is not None)
    return {
        "n": len(values),
        "mean_weighted": spend_weighted_mean(values, weights),
        "p25": _percentile(ordered, 25),
        "median": _percentile(ordered, 50),
        "p75": _percentile(ordered, 75),
    }


def derived(row):
    """Add CPM, CTR, play/view rate, CPA, ROAS to a canonical grain row.

    A15: this legacy grain carries plays but no completions measure,
    so its rate is the play/view rate under the honest id
    "view_rate" — never "vtr" (completions ÷ impressions, defined in
    Backend/creative_intel/analyst_metrics.py).
    """
    spend = row.get("spend", 0) or 0
    impr = row.get("impr", 0) or 0
    clicks = row.get("clicks", 0) or 0
    views = row.get("video_views", 0) or 0
    conv = row.get("conversions", 0) or 0
    rev = row.get("revenue", 0) or 0
    row["cpm"] = spend / impr * 1000 if impr else 0.0
    row["ctr"] = clicks / impr if impr else 0.0
    row["view_rate"] = views / impr if impr else 0.0
    row["cpa"] = spend / conv if conv else 0.0
    row["roas"] = rev / spend if spend else 0.0
    return row


def cohort_benchmark(rows, metric, pooled=None):
    """Benchmark one metric over cohort rows.

    Each row needs metric value, spend, creative_id, project.
    Returns status ok | insufficient, stats, and fallback when pooled given.
    """
    values = [r[metric] for r in rows]
    weights = [r.get("spend", 0) or 0 for r in rows]
    creatives = {r.get("creative_id") for r in rows}
    projects = {r.get("project") for r in rows}
    stats = describe(values, weights)
    stats["creatives"] = len(creatives)
    stats["projects"] = len(projects)
    if len(creatives) >= MIN_CREATIVES and len(projects) >= MIN_PROJECTS:
        return {"status": "ok", "stats": stats, "fallback_used": False}
    result = {"status": "insufficient", "stats": stats, "fallback_used": False}
    if pooled:
        result["fallback"] = describe(
            [r[metric] for r in pooled],
            [r.get("spend", 0) or 0 for r in pooled],
        )
        result["fallback_used"] = True
    return result


def rank_creatives(rows, metric, higher_is_better=False, min_spend=0):
    """Rank creatives by a metric; rows below min_spend sort last."""
    scored = []
    for row in rows:
        eligible = (row.get("spend", 0) or 0) >= min_spend
        scored.append((row.get(metric, 0), row, eligible))

    def _rank_key(item):
        value, _row, eligible = item
        # Missing metrics sort after every measured value, never as zero.
        if value is None:
            metric_key = (1, 0.0)
        elif higher_is_better:
            metric_key = (0, -value)
        else:
            metric_key = (0, value)
        return (0 if eligible else 1, metric_key)

    scored.sort(key=_rank_key)
    return [row for _, row, _ in scored]

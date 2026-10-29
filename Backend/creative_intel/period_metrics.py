"""Pure period-metric comparisons, independent of data selection and storage."""

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
MONEY_METRICS = frozenset({"spend", "revenue", "cpc", "cpm", "cpa", "roas"})
MANUAL_PERIOD_METRICS = (
    "spend", "impressions", "clicks", "conversions", "cpm", "vtr",
    "view_rate", "ctr", "cpc", "cpa", "roas",
)
MANUAL_MONEY_METRICS = frozenset({"spend", "cpc", "cpm", "cpa"})


def _currency_snapshot(pooled):
    """Copy only source-currency metadata; missing metadata stays unknown."""
    snapshot = {key: pooled.get(key) for key in (
        "currency", "currencies", "mixed_currency", "currency_known", "unknown_currency_contribution",
    )}
    if isinstance(snapshot["currencies"], (list, tuple)):
        snapshot["currencies"] = list(snapshot["currencies"])
    return snapshot


def _known_currency(snapshot):
    if (snapshot["currency_known"] is not True or snapshot["mixed_currency"] is not False
            or snapshot["unknown_currency_contribution"] is not False):
        return None
    currency = snapshot["currency"]
    declared = snapshot["currencies"]
    if not isinstance(currency, str) or not currency.strip() or not isinstance(declared, list):
        return None
    code = currency.strip().upper()
    if not declared or any(not isinstance(item, str) or item.strip().upper() != code for item in declared):
        return None
    return code


def period_currency_context(cur_pooled, prev_pooled):
    """Expose each period's denomination without changing comparison arithmetic.

    same_known_currency describes explicitly supported unit metadata. It is
    not an FX conversion and does not rewrite the legacy unspecified-currency
    calculation policy. Consumers must still handle unknown or mixed units.
    """
    current, previous = _currency_snapshot(cur_pooled), _currency_snapshot(prev_pooled)
    cur_code, prev_code = _known_currency(current), _known_currency(previous)
    return {"current": current, "previous": previous,
            "same_known_currency": cur_code is not None and cur_code == prev_code}


def _explicitly_unspecified(snapshot):
    """True for producer scopes that explicitly declare no currency."""
    currency = snapshot["currency"]
    return (snapshot["currencies"] == []
            and snapshot["mixed_currency"] is False
            and (currency is None
                 or (isinstance(currency, str) and not currency.strip())))


def manual_period_deltas(a_kpis, b_kpis):
    """B-minus-A deltas, requiring comparable units for native money.

    Preserve each side's native values and dimensionless/count arithmetic.
    ROAS is dimensionless once measured within a side. Matching known units
    compare directly; two explicitly unspecified producer scopes keep the
    legacy arithmetic without inventing a denomination. Absent metadata,
    known-plus-unknown mixes and different known units stay unavailable.
    Reasons are stable codes for localized consumer explanations; no FX occurs.
    """
    context = period_currency_context(b_kpis, a_kpis)
    same_currency = context["same_known_currency"] or (
        _explicitly_unspecified(context["current"])
        and _explicitly_unspecified(context["previous"]))
    delta, reasons = {}, {}
    for metric in MANUAL_PERIOD_METRICS:
        va, vb = a_kpis.get(metric), b_kpis.get(metric)
        if metric in MANUAL_MONEY_METRICS and not same_currency:
            delta[metric] = None
            reasons[metric] = "incomparable_currency"
        else:
            delta[metric] = round(vb - va, 4) if va is not None and vb is not None else None
    return delta, reasons


def _metric_value(sums, pooled, metric):
    """Return nullable raw totals or the caller's already-pooled ratio."""
    if metric in sums:
        value = sums[metric]
        if value is not None and metric in {"spend", "revenue"}:
            return round(value, 2)
        return value
    return pooled.get(metric)


def _money_comparable(cur_pooled, prev_pooled):
    """Preserve the existing single-currency and legacy-unspecified policy."""
    if cur_pooled.get("mixed_currency") or prev_pooled.get("mixed_currency"):
        return False
    return cur_pooled.get("currency") == prev_pooled.get("currency")


def _compare_values(current, previous, prev_has_rows=False):
    """Compare measured values without turning an undefined value into zero.

    prev_has_rows remains accepted for existing callers. Row presence cannot
    establish a previous measurement, including a ratio with a zero denominator.
    """
    if current is None or previous is None:
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


def compare_metric(current, previous, metric, prev_has_rows=False, *,
                   current_reported=True, previous_reported=True):
    """Return the comparison payload without calling unreported values 'new'.

    Period aggregation supplies reporting flags from raw availability and ratio
    row coverage. A None value stays unavailable even without those flags.
    """
    current = current if current_reported else None
    previous = previous if previous_reported else None
    if not current_reported or not previous_reported:
        state, pct, direction = "none", None, "flat"
    else:
        state, pct, direction = _compare_values(current, previous, prev_has_rows)
    return {
        "current": current,
        "previous": previous,
        "percent_change": pct,
        "direction": direction,
        "sentiment": _sentiment(metric, direction) if state == "compared" else "neutral",
        "state": state,
        "abs_change": round(current - previous, 4) if current is not None and previous is not None else None,
    }


def _metric_reported(sums, pooled, metric):
    if metric in sums:
        return sums[metric] is not None
    coverage = pooled.get("metric_coverage", {}).get(metric)
    # Missing coverage metadata alone does not erase a provided measurement.
    return coverage is None or coverage["reporting_rows"] > 0


def compare_period_metrics(cur_sums, prev_sums, cur_pooled, prev_pooled):
    """Compare already-selected periods; no I/O or selection occurs here.

    Counts describe reporting rows, not weighted population coverage. A null
    ratio stays unavailable, including when its denominator is a reported zero.
    Numeric ratios can still be compared without coverage metadata.
    """
    cur_has_rows = bool(cur_sums["n_ads"])
    prev_has_rows = bool(prev_sums["n_ads"])
    money_ok = _money_comparable(cur_pooled, prev_pooled)
    metrics = {}
    for metric in COMPARED_METRICS:
        cur_val = _metric_value(cur_sums, cur_pooled, metric) if cur_has_rows else None
        prev_val = _metric_value(prev_sums, prev_pooled, metric) if prev_has_rows else None
        if metric in MONEY_METRICS and not money_ok:
            if not cur_has_rows or not prev_has_rows:
                # Preserve own single-currency facts when the other side is
                # empty. A mixed side itself remains unmeasurable.
                if cur_pooled.get("mixed_currency"):
                    cur_val = None
                if prev_pooled.get("mixed_currency"):
                    prev_val = None
            else:
                cur_val, prev_val = None, None
        metrics[metric] = compare_metric(
            cur_val, prev_val, metric, prev_has_rows=prev_has_rows,
            current_reported=_metric_reported(cur_sums, cur_pooled, metric),
            previous_reported=_metric_reported(prev_sums, prev_pooled, metric),
        )
    return metrics

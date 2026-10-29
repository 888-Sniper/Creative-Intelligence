"""Pure metric comparisons using explicit native-currency metadata.

No conversion is inferred. Cost comparisons require one known denomination
across the candidates that actually have a value for that metric. Dimensionless
metrics retain their existing comparison policy.
"""

import math

COST_METRICS = frozenset({"cpa", "cpc", "cpm"})
MONETARY_METRICS = COST_METRICS | {"spend"}
NO_COMPARABLE_METRIC = "No comparable performance metric is available."
NO_DELIVERY = "Neither creative has delivery data yet."


def cost_comparison_reason(groups, metric):
    """Explain an unavailable native-cost or spend comparison, or return None.

    These are aggregate metadata records, not raw spend rows. Older producers
    may omit currency_known; an explicit currency plus consistent metadata
    still establishes its unit. An explicit false flag does not.
    """
    if metric not in MONETARY_METRICS:
        return None
    reason = ("%s comparison unavailable: amounts have different or unknown"
              " currencies." % metric.upper())
    currencies = set()
    for group in groups:
        if group.get(metric) is None:
            continue
        currency = group.get("currency")
        if not isinstance(currency, str) or not currency.strip():
            return reason
        code = currency.strip().upper()
        if (group.get("mixed_currency") or group.get("unknown_currency_contribution")
                or group.get("currency_known") is False):
            return reason
        declared = group.get("currencies")
        if declared is not None:
            if not isinstance(declared, (list, tuple)):
                return reason
            if any(not isinstance(item, str) or item.strip().upper() != code
                   for item in declared):
                return reason
        currencies.add(code)
    return reason if len(currencies) > 1 else None


def rank_creatives(keys, per, rank_by, *, higher):
    """Return display order and winner, withholding incomparable cost rankings.

    Unavailable comparisons keep the input display order and have no winner.
    Missing values otherwise remain last, with stable tie ordering.
    """
    if cost_comparison_reason([per.get(key, {}) for key in keys], rank_by):
        return list(keys), None

    def sort_key(key):
        value = per.get(key, {}).get(rank_by)
        if value is None:
            return (1, 0.0)
        return (0, -value if higher else value)

    ranking = sorted(keys, key=sort_key)
    if all(per.get(key, {}).get(rank_by) is None for key in ranking):
        return ranking, None
    return ranking, ranking[0]


def unavailable_campaign_cost_comparison(per, rank_by):
    """Return the established no-winner payload for incomparable native costs.

    Empty/single-campaign and all-missing-metric cases remain the caller's
    existing contracts. The producer's display order and native KPIs survive.
    """
    if len(per) < 2:
        return None
    reason = cost_comparison_reason(per.values(), rank_by)
    if reason is None:
        return None
    return {
        "kpis": per, "ranking": list(per), "rank_by": rank_by, "winner": None,
        "why": {"metric": rank_by, "top": None, "bottom": None,
                "differences": [reason], "details": {}},
    }


def campaign_spend_note(top_name, bottom_name, top, bottom, formatter):
    """Describe comparable native spend, preserving amounts and their owners.

    The formatter must take an amount and its explicit currency. Unavailable
    comparisons return a reason without a numeric scale claim or details.
    """
    spend_top, spend_bottom = top.get("spend"), bottom.get("spend")
    try:
        number_top, number_bottom = float(spend_top), float(spend_bottom)
    except (TypeError, ValueError, OverflowError):
        return "Spend comparison unavailable: reported spend is missing or invalid.", None
    if not math.isfinite(number_top) or not math.isfinite(number_bottom):
        return "Spend comparison unavailable: reported spend is missing or invalid.", None
    reason = cost_comparison_reason([top, bottom], "spend")
    if reason:
        return reason, None
    if number_top == number_bottom:
        return None, None
    bigger = top_name if number_top > number_bottom else bottom_name
    note = ("Scale differs: %s spent %s vs %s %s (%s has higher native spend)"
            % (top_name, formatter(spend_top, top["currency"]),
               bottom_name, formatter(spend_bottom, bottom["currency"]), bigger))
    return note, {"top": spend_top, "bottom": spend_bottom}


def pairwise_metric_notes(a, b, da, db):
    """Preserve measured-delta notes without comparing incompatible cost units."""
    differences = []
    for metric, higher in (("cpa", False), ("ctr", True), ("vtr", True),
                           ("cpc", False), ("cpm", False), ("roas", True)):
        va, vb = da.get(metric), db.get(metric)
        if va is None or vb is None:
            if (va is None) != (vb is None):
                differences.append(
                    "%s is not measurable for %s (insufficient data)"
                    % (metric.upper(), a if va is None else b))
            continue
        reason = cost_comparison_reason([da, db], metric)
        if reason:
            differences.append(reason)
            continue
        if va == vb:
            continue
        winner = a if (va > vb) == higher else b
        winner_value, other_value = (va, vb) if winner == a else (vb, va)
        differences.append("%s leads %s on %s (%s vs %s)"
                           % (winner, b if winner == a else a,
                              metric.upper(), winner_value, other_value))
    return differences


def multi_metric_notes(keys, datas):
    """Preserve N-way leaders only for comparable available metric values."""
    differences = []
    for metric, higher in (("cpa", False), ("cpc", False),
                           ("cpm", False), ("ctr", True),
                           ("vtr", True), ("roas", True)):
        valued = [(key, datas.get(key, {}).get(metric)) for key in keys]
        valued = [(key, value) for key, value in valued if value is not None]
        reason = cost_comparison_reason([datas.get(key, {}) for key, _ in valued], metric)
        if reason:
            differences.append(reason)
            continue
        if len({value for _, value in valued}) < 2:
            continue
        best = (max if higher else min)(valued, key=lambda item: item[1])
        differences.append("%s leads on %s (%s vs %s)" % (
            best[0], metric.upper(), best[1],
            ", ".join("%s %s" % (key, value) for key, value in valued if key != best[0])))
    return differences


def pairwise_primary_winner(a, b, da, db):
    """Retain the legacy CPA/CTR preference with a native-cost boundary."""
    if (da.get("conversions") or 0) > 0 and (db.get("conversions") or 0) > 0:
        cpa_a, cpa_b = da.get("cpa"), db.get("cpa")
        if cpa_a is not None and cpa_b is not None:
            reason = cost_comparison_reason([da, db], "cpa")
            if reason:
                return None, reason
            return (a if cpa_a <= cpa_b else b), None
        return None, NO_COMPARABLE_METRIC
    if (da.get("impressions") or 0) > 0 or (db.get("impressions") or 0) > 0:
        return (a if (da.get("ctr", 0) or 0) >= (db.get("ctr", 0) or 0) else b), None
    return None, NO_DELIVERY


def multi_primary_winner(keys, datas):
    """Retain the legacy CPA/CTR preference without cross-unit CPA winners."""
    converting = [key for key in keys if (datas.get(key, {}).get("conversions") or 0) > 0]
    if converting:
        ranked = [(key, datas[key].get("cpa")) for key in converting
                  if datas.get(key, {}).get("cpa") is not None]
        if ranked:
            reason = cost_comparison_reason([datas[key] for key, _ in ranked], "cpa")
            if reason:
                return None, reason
            return min(ranked, key=lambda item: item[1])[0], None
        return None, NO_COMPARABLE_METRIC
    shown = [(key, datas.get(key, {}).get("ctr")) for key in keys]
    shown = [(key, value) for key, value in shown if value is not None]
    if shown:
        return max(shown, key=lambda item: item[1])[0], None
    return None, NO_DELIVERY

"""Pure availability rules for canonical rows and matched-population ratios."""

import json


def missing_fields(row):
    """Preserve canonical missing markers and the documented legacy fallback."""
    try:
        return set(json.loads(row.get("missing_json") or "[]"))
    except (ValueError, TypeError):
        return set()


def reported_raw_totals(rows):
    """Sum supplied raw fields, retaining None when no row reported a field.

    A partial total contains only its reporting rows; it is not an estimate
    for the entire population. As with ratios, absent legacy markers retain
    the previous measured-zero interpretation.
    """
    rows = list(rows or [])
    prepared = [(row, missing_fields(row)) for row in rows]
    totals = {"n_ads": len(rows)}
    for field in ("spend", "impressions", "clicks", "conversions", "video_views", "revenue"):
        values = [row.get(field, 0) or 0 for row, missing in prepared if field not in missing]
        totals[field] = sum(values) if values else None
    return totals


def reported_ratio_components(rows, numerator, denominator):
    """Return additive components for exactly the matched reporting rows.

    Stored zeroes are measured unless missing_json says otherwise. Rows from
    before missing-data tracking retain their legacy zero interpretation.
    Coverage counts rows, not impressions, spend, or another weighted unit.
    """
    rows = list(rows or [])
    required = {numerator, denominator}
    usable = [row for row in rows if not required.intersection(missing_fields(row))]
    return {
        "numerator": sum(row.get(numerator, 0) or 0 for row in usable),
        "denominator": sum(row.get(denominator, 0) or 0 for row in usable),
        "reporting_rows": len(usable), "total_rows": len(rows),
    }


def pooled_reported_ratio(rows, numerator, denominator, scale=1.0):
    """Return a ratio plus explicit row coverage for its matched population."""
    component = reported_ratio_components(rows, numerator, denominator)
    den = component["denominator"]
    value = component["numerator"] / den * scale if den else None
    return value, {key: component[key] for key in ("reporting_rows", "total_rows")}


def reported_common_kpis(rows):
    """Canonical CTR/cost ratios and their explicit reporting-row counts."""
    ratios, coverage, _ = reported_common_kpi_details(rows)
    return ratios, coverage


def reported_common_kpi_details(rows):
    """Ratios, row coverage and unrounded components for downstream pooling."""
    rows = list(rows or [])
    ratios = {}
    coverage = {}
    components = {}
    for metric, numerator, denominator, scale, places in (
        ("ctr", "clicks", "impressions", 1.0, 4),
        ("cpc", "spend", "clicks", 1.0, 2),
        ("cpm", "spend", "impressions", 1000.0, 2),
        ("cpa", "spend", "conversions", 1.0, 2),
    ):
        component = reported_ratio_components(rows, numerator, denominator)
        den = component["denominator"]
        value = component["numerator"] / den * scale if den else None
        ratios[metric] = round(value, places) if value is not None else None
        coverage[metric] = {key: component[key] for key in ("reporting_rows", "total_rows")}
        components[metric] = component
    return ratios, coverage, components


def reported_roas_details(rows):
    """Preserve the canonical revenue-reporting ROAS population and precision.

    The existing revenue_reported flag defines this population. Total spend
    is included only to describe spend coverage, never as the ROAS divisor.
    Currency comparability remains the responsibility of the scope caller.
    """
    rows = list(rows or [])
    total_spend = sum((row or {}).get("spend", 0) or 0 for row in rows)
    reported = [row for row in rows if (row or {}).get("revenue_reported")]
    spend = sum((row or {}).get("spend", 0) or 0 for row in reported)
    revenue = sum((row or {}).get("revenue", 0) or 0 for row in reported)
    coverage = spend / total_spend if total_spend > 0 else None
    value = round(revenue / spend, 4) if spend > 0 else None
    return value, coverage, {
        "numerator": revenue, "denominator": spend,
        "reporting_rows": len(reported), "total_rows": len(rows),
        "total_spend": total_spend,
    }

"""Creative analysis: validate annotations, join metrics, compare elements.

Works on verified annotations only for client-facing output; drafts stay
in review. All CPA comparisons are spend-weighted, never average-of-ratios.
"""

import math

from benchmarks import derived, spend_weighted_mean

HOOK_TYPES = {"visual", "spoken", "text"}
FORMATS = {"creator", "branded"}
NUMERIC = {"duration_s", "product_first_visible_s", "brand_first_visible_s",
           "brand_first_audible_s", "confidence"}
EARLY_PRODUCT_S = 3.0


def load_annotations(path):
    import csv
    rows = []
    with open(path) as fh:
        for raw in csv.DictReader(fh):
            row = {}
            for key, val in raw.items():
                if key in NUMERIC:
                    try:
                        row[key] = float(val)
                    except (TypeError, ValueError):
                        row[key] = None
                elif key == "human_verified":
                    row[key] = str(val).strip().lower() == "true"
                else:
                    row[key] = str(val).strip()
            rows.append(row)
    return rows


def validate(ann):
    """Return a list of data errors; empty means structurally valid."""
    errors = []
    if not ann.get("creative_id"):
        errors.append("missing creative_id")
    if ann.get("hook_type") not in HOOK_TYPES:
        errors.append(f"bad hook_type: {ann.get('hook_type')}")
    if ann.get("creator_vs_branded") not in FORMATS:
        errors.append(f"bad format: {ann.get('creator_vs_branded')}")
    for field in ("duration_s", "product_first_visible_s",
                  "brand_first_visible_s"):
        val = ann.get(field)
        if val is not None and val < 0:
            errors.append(f"negative {field}")
    if not ann.get("cta"):
        errors.append("missing cta")
    return errors


def needs_review(anns):
    """Drafts: invalid rows plus valid-but-unverified rows."""
    return [a for a in anns
            if validate(a) or not a.get("human_verified")]


def verified(anns):
    return [a for a in anns
            if not validate(a) and a.get("human_verified")]


def join_metrics(anns, grain_rows):
    """Attach metrics onto annotations, aggregating every grain row that
    shares a creative (multi-day runs) and recomputing ratios from totals
    instead of averaging them."""
    sums, tags = {}, {}
    for row in grain_rows:
        cid = row["creative_id"]
        acc = sums.setdefault(cid, {"spend": 0.0, "impr": 0.0, "clicks": 0.0,
                                    "video_views": 0.0, "conversions": 0.0,
                                    "revenue": 0.0})
        for key in acc:
            acc[key] += row.get(key, 0) or 0
        tags.setdefault(cid, row)
    joined = []
    for ann in anns:
        cid = ann["creative_id"]
        if cid not in sums:
            continue
        # Grain first for cohort tags (funnel, vertical, market, ...),
        # annotation wins on creative attributes, metrics attached last.
        joined.append({**tags[cid], **ann, **derived(dict(sums[cid]))})
    return joined


def weighted_cpa(rows):
    return spend_weighted_mean([r["cpa"] for r in rows],
                               [r.get("spend", 0) or 0 for r in rows])


def _seconds(value):
    """Numeric seconds or None. Non-numeric junk never reaches a comparison."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def early_vs_late(joined, field="product_first_visible_s",
                  threshold=EARLY_PRODUCT_S):
    early = [r for r in joined
             if (_seconds(r.get(field)) is not None
                 and _seconds(r.get(field)) <= threshold)]
    late = [r for r in joined
            if (_seconds(r.get(field)) is not None
                and _seconds(r.get(field)) > threshold)]
    return {
        "field": field,
        "threshold_s": threshold,
        "early_n": len(early),
        "late_n": len(late),
        "early_cpa": weighted_cpa(early) if early else 0.0,
        "late_cpa": weighted_cpa(late) if late else 0.0,
    }


def best_by_element(joined, element):
    """Spend-weighted CPA per distinct element value, best first."""
    groups = {}
    for row in joined:
        groups.setdefault(row.get(element), []).append(row)
    ranked = [(weighted_cpa(rows), value, len(rows))
              for value, rows in groups.items()]
    ranked.sort()
    return [{"value": v, "cpa": c, "n": n} for c, v, n in ranked]


def recommend(joined):
    """Specific next-step recommendations grounded in the joined data."""
    out = []
    hooks = best_by_element(joined, "hook_type")
    if hooks:
        out.append(f"Best hook type is {hooks[0]['value']} "
                   f"(weighted CPA {hooks[0]['cpa']:.2f} across "
                   f"{hooks[0]['n']} creatives). Brief more of these first.")
    timing = early_vs_late(joined)
    if timing["early_n"] and timing["late_n"]:
        if timing["early_cpa"] < timing["late_cpa"]:
            out.append(f"Showing the product before second "
                       f"{timing['threshold_s']:.0f} wins "
                       f"({timing['early_cpa']:.2f} vs "
                       f"{timing['late_cpa']:.2f} CPA). Test 3 more "
                       f"variations with the product in the first 3 seconds.")
        else:
            out.append("Late product appearance wins in this set; "
                       "retest with a larger cohort before briefing.")
    ctas = best_by_element(joined, "cta")
    if ctas:
        out.append(f"Best CTA is {ctas[0]['value']} "
                   f"(weighted CPA {ctas[0]['cpa']:.2f}). "
                   f"Standardise on it for the next test round.")
    return out

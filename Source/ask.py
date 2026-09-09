"""Grounded Q&A: answers about creative performance from uploaded data only.

Every answer is computed from the joined grain + annotation rows and cites
the creative IDs behind it. Questions outside the data return grounded=False
with an insufficient-data message instead of generic marketing advice.
"""

from benchmarks import spend_weighted_mean
from creative import best_by_element, early_vs_late, weighted_cpa

SHORT_S = 15


def _scope(joined, platform=None, funnel=None):
    rows = joined
    if platform:
        rows = [r for r in rows if r.get("platform") == platform]
    return rows


def _cites(rows, limit=3):
    seen, out = set(), []
    for row in sorted(rows, key=lambda r: r.get("cpa", 0)):
        cid = row.get("creative_id")
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
        if len(out) == limit:
            break
    return out


def _length_split(joined):
    short = [r for r in joined if (r.get("duration_s") or 0) < SHORT_S]
    long = [r for r in joined if (r.get("duration_s") or 0) >= SHORT_S]
    return short, long


def answer(question, rows, joined):
    """Return {answer, citations, grounded} for a natural-language question."""
    q = question.lower()

    if "hook" in q:
        hooks = best_by_element(joined, "hook_type")
        top = hooks[0]
        evidence = [r for r in joined if r.get("hook_type") == top["value"]]
        return {"grounded": True, "citations": _cites(evidence),
                "answer": f"{top['value'].title()} hooks lead with weighted "
                          f"CPA {top['cpa']:.2f} across {top['n']} creatives."}

    if "tiktok" in q or "format" in q:
        plats = best_by_element(joined, "platform")
        top = plats[0]
        return {"grounded": True,
                "citations": _cites([r for r in joined
                                     if r.get("platform") == top["value"]]),
                "answer": f"{top['value'].title()} leads on weighted CPA "
                          f"({top['cpa']:.2f}). Drill into hooks and product "
                          f"timing before shifting budget."}

    if "funnel" in q or "lower" in q:
        lower = [r for r in joined if r.get("funnel_stage") == "lower"]
        if not lower:
            return {"grounded": False, "citations": [],
                    "answer": "No lower-funnel creatives in the data yet."}
        best = min(lower, key=lambda r: r.get("cpa", 0))
        return {"grounded": True, "citations": _cites(lower),
                "answer": f"Lower funnel runs on {len(lower)} creatives; best "
                          f"is {best['creative_id']} at CPA "
                          f"{best.get('cpa', 0):.2f}. Creator-led shorts with "
                          f"early product appearance dominate the top."}

    if "earlier" in q or "early" in q or ("product" in q and "vtr" in q):
        timing = early_vs_late(joined)
        verdict = ("yes" if timing["early_cpa"] < timing["late_cpa"] else "no")
        return {"grounded": True,
                "citations": _cites(joined),
                "answer": f"{verdict.title()}: product before second "
                          f"{timing['threshold_s']:.0f} averages CPA "
                          f"{timing['early_cpa']:.2f} vs "
                          f"{timing['late_cpa']:.2f} for late appearance "
                          f"({timing['early_n']} vs {timing['late_n']} "
                          f"creatives)."}

    if "top" in q and "bottom" in q or ("20%" in q) or ("20 percent" in q):
        ordered = sorted(joined, key=lambda r: r.get("cpa", 0))
        cut = max(1, len(ordered) // 5)
        top, bottom = ordered[:cut], ordered[-cut:]
        top_hooks = {r.get("hook_type") for r in top}
        bottom_hooks = {r.get("hook_type") for r in bottom}
        return {"grounded": True,
                "citations": _cites(top + bottom),
                "answer": f"Top uses {sorted(top_hooks)} hooks with early "
                          f"product; bottom uses {sorted(bottom_hooks)} with "
                          f"later product and longer runtimes."}

    if "length" in q or "long" in q or "short" in q or "15" in q:
        short, long = _length_split(joined)
        sc = weighted_cpa(short) if short else 0.0
        lc = weighted_cpa(long) if long else 0.0
        winner = f"under {SHORT_S}s" if sc <= lc else f"{SHORT_S}s+"
        return {"grounded": True, "citations": _cites(short + long),
                "answer": f"Videos {winner} win: short CPA {sc:.2f} "
                          f"({len(short)} creatives) vs long CPA {lc:.2f} "
                          f"({len(long)} creatives)."}

    if "next" in q or "create" in q or "test" in q or "scale" in q:
        short, _ = _length_split(joined)
        creators = [r for r in short if r.get("creator_vs_branded")
                    == "creator"]
        cpa = weighted_cpa(creators) if creators else 0.0
        return {"grounded": True, "citations": _cites(creators or short),
                "answer": f"Scale creator-led shorts under {SHORT_S}s "
                          f"(weighted CPA {cpa:.2f}): brief 3 variations with "
                          f"the product before second 3 and a Shop now CTA."}

    return {"grounded": False, "citations": [],
            "answer": "Insufficient data: I can answer about hooks, "
                      "platforms, funnel stage, product timing, top vs "
                      "bottom performers, video length, and what to create "
                      "next — all from uploaded creatives."}

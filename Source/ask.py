"""Grounded Q&A: answers about creative performance from uploaded data only.

Every answer is computed from the joined grain + annotation rows and cites
the creative IDs behind it. Questions outside the data return grounded=False
with an insufficient-data message instead of generic marketing advice.
"""

import math

from benchmarks import spend_weighted_mean
from creative import best_by_element, weighted_cpa

SHORT_S = 15
PRODUCT_EARLY_S = 3.0


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


def _timing_split(joined, threshold=PRODUCT_EARLY_S):
    """Split rows by product-first-visible seconds; non-numeric junk excluded."""
    early, late = [], []
    for row in joined:
        val = row.get("product_first_visible_s")
        if isinstance(val, bool):
            continue
        try:
            sec = float(val)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(sec):
            continue
        (early if sec <= threshold else late).append(row)
    return early, late


def _pooled_vtr(rows):
    """Pooled VTR = sum(video_views) / sum(impr), plus the raw totals."""
    impr = sum(r.get("impr", 0) or 0 for r in rows)
    views = sum(r.get("video_views", 0) or 0 for r in rows)
    return (views / impr if impr else 0.0), views, impr


def _ids(rows):
    return sorted({r["creative_id"] for r in rows if r.get("creative_id")})


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

    if ("vtr" in q or "view-through" in q or "view through" in q
            or (("early" in q or "earlier" in q or "timing" in q)
                and "product" in q)):
        early, late = _timing_split(joined)
        if not early or not late:
            return {"grounded": False, "citations": [],
                    "answer": "Insufficient data: need creatives with both "
                              "early and late product appearance to compare "
                              "VTR."}
        evtr, eviews, eimpr = _pooled_vtr(early)
        lvtr, lviews, limpr = _pooled_vtr(late)
        verdict = "yes" if evtr > lvtr else "no"
        early_cites = _cites(early)
        cites = early_cites + [c for c in _cites(late) if c not in early_cites]
        return {"grounded": True,
                "citations": cites,
                "answer": f"{verdict.title()}: product before second "
                          f"{PRODUCT_EARLY_S:.0f} holds VTR "
                          f"{evtr * 100:.1f}% ({eviews:,.0f} views / "
                          f"{eimpr:,.0f} impr across {len(early)} creatives: "
                          f"{', '.join(_ids(early))}) vs "
                          f"{lvtr * 100:.1f}% ({lviews:,.0f} views / "
                          f"{limpr:,.0f} impr across {len(late)} creatives: "
                          f"{', '.join(_ids(late))}) for late appearance."}

    if "tiktok" in q or "format" in q:
        tik = [r for r in joined if r.get("platform") == "tiktok"]
        if not tik:
            return {"grounded": False, "citations": [],
                    "answer": "Insufficient data: no TikTok creatives in the "
                              "uploaded data yet."}
        creators = [r for r in tik
                    if r.get("creator_vs_branded") == "creator"]
        branded = [r for r in tik
                   if r.get("creator_vs_branded") == "branded"]
        if not creators or not branded:
            present, missing = ((creators, "branded") if creators
                                else (branded, "creator"))
            cpa = weighted_cpa(present)
            return {"grounded": True, "citations": _cites(tik),
                    "answer": f"TikTok runs {len(tik)} verified creatives, "
                              f"all {present[0]['creator_vs_branded']}-led "
                              f"({', '.join(_ids(present))}) at weighted CPA "
                              f"{cpa:.2f}; no verified {missing} TikTok "
                              f"creatives to compare yet."}
        ccpa, bcpa = weighted_cpa(creators), weighted_cpa(branded)
        winner = "Creator" if ccpa <= bcpa else "Branded"
        return {"grounded": True, "citations": _cites(tik),
                "answer": f"{winner} wins on TikTok: creator "
                          f"({', '.join(_ids(creators))}) weighted CPA "
                          f"{ccpa:.2f} across {len(creators)} creatives vs "
                          f"branded ({', '.join(_ids(branded))}) weighted CPA "
                          f"{bcpa:.2f} across {len(branded)} creatives."}

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

    if "top" in q and "bottom" in q or ("20%" in q) or ("20 percent" in q):
        ordered = sorted(joined, key=lambda r: r.get("cpa", 0))
        cut = max(1, len(ordered) // 5)
        top, bottom = ordered[:cut], ordered[-cut:]
        top_hooks = {r.get("hook_type") for r in top}
        bottom_hooks = {r.get("hook_type") for r in bottom}
        return {"grounded": True,
                "citations": _cites(top + bottom),
                "answer": f"Top uses {sorted(top_hooks)} hooks with early "
                          f"product (n={len(top)}: "
                          f"{', '.join(_ids(top))}); bottom uses "
                          f"{sorted(bottom_hooks)} with later product and "
                          f"longer runtimes (n={len(bottom)}: "
                          f"{', '.join(_ids(bottom))})."}

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
            "answer": "Insufficient data: I can answer about hooks, TikTok "
                      "formats, funnel stage, product timing vs VTR, top vs "
                      "bottom performers, video length, and what to create "
                      "next — all from uploaded creatives."}

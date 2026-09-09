"""Spend-weighted benchmarks over the canonical ads dataset."""

GROUPABLE = ("platform", "campaign", "hook_type", "creator_vs_branded")


def _weight(rows, metric):
    spend = sum(r["spend"] for r in rows)
    if spend <= 0:
        return 0.0
    return sum(r["spend"] * r[metric] for r in rows) / spend


def summarize(rows):
    """Spend-weighted roll-up of ad rows sharing one group key."""
    spend = sum(r["spend"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    return {
        "n_ads": len(rows),
        "spend": round(spend, 2),
        "impressions": impr,
        "ctr": round(clicks / impr, 4) if impr else 0.0,
        "cpc": round(spend / clicks, 2) if clicks else 0.0,
        "conv_rate_weighted": round(_weight(rows, "conv_rate"), 4),
        "cpa": round(spend / conv, 2) if conv else 0.0,
    }


def _enrich(conn, rows):
    """Attach hook_type / creator_vs_branded from annotations ('' if none)."""
    out = []
    for r in rows:
        got = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (r["creative_key"],)).fetchone()
        hook, cvb = "", ""
        if got:
            import json
            try:
                ann = json.loads(got[0])
                hook = ann.get("hook_type", "") or ""
                cvb = ann.get("creator_vs_branded", "") or ""
            except ValueError:
                pass
        impr = r["impressions"] or 0
        d = dict(r)
        d["hook_type"] = hook
        d["creator_vs_branded"] = cvb
        d["conv_rate"] = (r["conversions"] / impr) if impr else 0.0
        out.append(d)
    return out


def benchmark(conn, group_by="hook_type"):
    if group_by not in GROUPABLE:
        raise ValueError("group_by must be one of %s" % (sorted(GROUPABLE),))
    conn.row_factory = None
    cols = [c[0] for c in conn.execute("SELECT * FROM ads LIMIT 0").description]
    rows = [dict(zip(cols, v)) for v in conn.execute("SELECT * FROM ads").fetchall()]
    rows = _enrich(conn, rows)
    groups = {}
    for r in rows:
        groups.setdefault(r[group_by] or "(unannotated)", []).append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}

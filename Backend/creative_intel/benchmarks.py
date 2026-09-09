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


def benchmark(conn, group_by="hook_type", filters=None):
    if group_by not in GROUPABLE:
        raise ValueError("group_by must be one of %s" % (sorted(GROUPABLE),))
    conn.row_factory = None
    cols = [c[0] for c in conn.execute("SELECT * FROM ads LIMIT 0").description]
    rows = [dict(zip(cols, v)) for v in conn.execute("SELECT * FROM ads").fetchall()]
    rows = _enrich(conn, rows)
    if filters:
        filt = normalize_filters(filters)
        rows = [r for r in rows if match_filters(r, filt)]
    groups = {}
    for r in rows:
        groups.setdefault(r[group_by] or "(unannotated)", []).append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


# === EXPERT 2 (COHORTS+COMPARE) EXTENSION — appended; original functions above untouched. ===
"""Multi-filter benchmark builder, campaign compare, and report helpers.

Filter axes: vertical / platform / funnel / objective / market / client,
plus include/exclude project lists. Rows are canonical ads rows enriched
with annotation fields; a filter on an axis only constrains rows carrying
that key (extra axes may arrive via annotations or future columns).
Project identity is row["project"] when present, else row["campaign"].
"""

FILTER_KEYS = ("vertical", "platform", "funnel", "objective", "market", "client")

KPI_KEYS = ("cpm", "vtr", "ctr", "cpa", "roas")

KPI_DIRECTIONS = {"cpm": "lower", "vtr": "higher", "ctr": "higher",
                  "cpa": "lower", "roas": "higher"}

MIN_ADS = 5
MIN_PROJECTS = 3
MIN_CREATIVES = MIN_ADS  # alias: one creative per ad row at minimum grain


def project_of(row):
    """Project identity for include/exclude lists (campaign fallback)."""
    return row.get("project") or row.get("campaign") or ""


def kpis_for_rows(rows):
    """Aggregate KPIs over ad rows (spend-weighted where it matters)."""
    spend = sum(r.get("spend", 0) or 0 for r in rows)
    impr = sum(r.get("impressions", 0) or 0 for r in rows)
    clicks = sum(r.get("clicks", 0) or 0 for r in rows)
    conv = sum(r.get("conversions", 0) or 0 for r in rows)
    views = sum(r.get("video_views", 0) or 0 for r in rows)
    revenue = sum(r.get("revenue", 0) or 0 for r in rows)
    return {
        "n_ads": len(rows),
        "spend": round(spend, 2),
        "impressions": impr,
        "clicks": clicks,
        "conversions": conv,
        "video_views": views,
        "cpm": round(spend / impr * 1000, 2) if impr else 0.0,
        "vtr": round(views / impr, 4) if impr else 0.0,
        "ctr": round(clicks / impr, 4) if impr else 0.0,
        "cpa": round(spend / conv, 2) if conv else 0.0,
        "roas": round(revenue / spend, 4) if spend else 0.0,
    }


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank = pct / 100 * (len(sorted_vals) - 1)
    low = int(rank)
    frac = rank - low
    high = min(low + 1, len(sorted_vals) - 1)
    return float(sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * frac)


def describe_bands(values, weights):
    """Spend-weighted mean plus p25/median/p75 bands for one metric."""
    ordered = sorted(values)
    total = sum(weights)
    mean = sum(v * w for v, w in zip(values, weights)) / total if total > 0 else 0.0
    return {
        "n": len(values),
        "mean_weighted": round(mean, 4),
        "p25": round(_percentile(ordered, 25), 4),
        "median": round(_percentile(ordered, 50), 4),
        "p75": round(_percentile(ordered, 75), 4),
    }


def _as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v) != ""]
    return [str(value)]


def normalize_filters(filters):
    """Validate and canonicalise a cohort filter dict."""
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError("filters must be an object")
    allowed = set(FILTER_KEYS) | {"include_projects", "exclude_projects"}
    unknown = sorted(set(filters) - allowed)
    if unknown:
        raise ValueError("unknown filter keys: %s" % unknown)
    out = {}
    for key in FILTER_KEYS:
        vals = _as_list(filters.get(key))
        if vals:
            out[key] = sorted(set(vals))
    for key in ("include_projects", "exclude_projects"):
        vals = _as_list(filters.get(key))
        if vals:
            out[key] = sorted(set(vals))
    return out


FILTER_FIELD = {"funnel": "funnel_stage"}


def match_filters(row, filters):
    """True when a row satisfies every active filter axis.

    Matching is case-insensitive; "funnel" reads the funnel_stage column.
    """
    for key in FILTER_KEYS:
        allowed = (filters or {}).get(key)
        if allowed:
            actual = str(row.get(FILTER_FIELD.get(key, key)) or "").lower()
            wanted = [str(v).lower() for v in allowed]
            if actual not in wanted:
                return False
    filt = filters or {}
    if filt.get("include_projects") and project_of(row) not in filt["include_projects"]:
        return False
    if filt.get("exclude_projects") and project_of(row) in filt["exclude_projects"]:
        return False
    return True


def all_rows(conn):
    """Every ads row, enriched with annotation fields + conv_rate."""
    conn.row_factory = None
    cols = [c[0] for c in conn.execute("SELECT * FROM ads LIMIT 0").description]
    rows = [dict(zip(cols, v)) for v in conn.execute("SELECT * FROM ads").fetchall()]
    return _enrich(conn, rows)


def _row_metric(row, metric):
    if metric in ("cpm", "vtr", "ctr", "cpa", "roas"):
        return kpis_for_rows([row])[metric]
    if metric not in row:
        raise ValueError("unknown metric %r (try %s)" % (metric, sorted(KPI_KEYS)))
    try:
        return float(row[metric] or 0)
    except (TypeError, ValueError):
        raise ValueError("metric %r is not numeric" % metric)


def benchmark_filtered(conn, filters=None, metric="cpa"):
    """Build a spend-weighted benchmark over the filtered cohort.

    Returns stats with p25/median/p75 bands plus a min-n guard:
    status "ok" needs >= MIN_ADS ads and >= MIN_PROJECTS projects,
    otherwise "insufficient".
    """
    if metric not in KPI_KEYS and metric not in ("spend", "conv_rate"):
        raise ValueError("metric must be one of %s" % (sorted(KPI_KEYS + ("spend", "conv_rate")),))
    filt = normalize_filters(filters)
    rows = [r for r in all_rows(conn) if match_filters(r, filt)]
    projects = sorted({project_of(r) for r in rows if project_of(r)})
    stats = describe_bands([_row_metric(r, metric) for r in rows],
                           [r.get("spend", 0) or 0 for r in rows])
    stats["projects"] = len(projects)
    status = ("ok" if stats["n"] >= MIN_ADS and stats["projects"] >= MIN_PROJECTS
              else "insufficient")
    return {"filters": filt, "metric": metric, "n_ads": stats["n"],
            "project_list": projects, "stats": stats, "status": status,
            "fallback_used": False,
            "kpis": kpis_for_rows(rows)}


def campaign_kpis(conn, campaigns=None, filters=None):
    """Per-campaign KPIs (CPM/VTR/CTR/CPA/ROAS) over enriched ad rows."""
    rows = all_rows(conn)
    if filters:
        filt = normalize_filters(filters)
        rows = [r for r in rows if match_filters(r, filt)]
    groups = {}
    for r in rows:
        groups.setdefault(r.get("campaign") or "(uncategorised)", []).append(r)
    if campaigns is not None:
        wanted = _as_list(campaigns)
        groups = {k: v for k, v in groups.items() if k in wanted}
    return {k: kpis_for_rows(v) for k, v in sorted(groups.items())}


def _campaign_elements(conn, campaign):
    """Distinct creative elements behind one campaign (for why-analysis)."""
    import json
    rows = [r for r in all_rows(conn) if (r.get("campaign") or "") == campaign]
    hook_types, modes, platforms = set(), set(), set()
    for r in rows:
        platforms.add(r.get("platform") or "")
        got = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (r.get("creative_key"),)).fetchone()
        if got:
            try:
                ann = json.loads(got[0])
            except ValueError:
                continue
            if ann.get("hook_type"):
                hook_types.add(ann["hook_type"])
            if ann.get("creator_vs_branded"):
                modes.add(ann["creator_vs_branded"])
        elif r.get("hook_type"):
            hook_types.add(r["hook_type"])
    return {"hook_types": sorted(hook_types), "creator_modes": sorted(modes),
            "platforms": sorted(p for p in platforms if p),
            "n_ads": len(rows),
            "n_creatives": len({r.get("creative_key") for r in rows})}


def compare_campaigns(conn, campaigns=None, rank_by="cpa"):
    """Compare campaigns: per-campaign KPIs plus a why-analysis.

    rank_by picks the ranking metric (lower-is-better for cpm/cpa,
    higher-is-better for vtr/ctr/roas). The why-analysis names which
    elements (hook_type, creator mode, platform mix, scale) differ
    between the top- and bottom-ranked campaigns.
    """
    if rank_by not in KPI_KEYS:
        raise ValueError("rank_by must be one of %s" % sorted(KPI_KEYS))
    per = campaign_kpis(conn, campaigns)
    if len(per) < 1:
        raise ValueError("no campaigns match %r" % (campaigns,))
    higher = KPI_DIRECTIONS[rank_by] == "higher"
    ranking = sorted(per, key=lambda c: per[c][rank_by], reverse=higher)
    top, bottom = ranking[0], ranking[-1]
    why = {"metric": rank_by, "top": top, "bottom": bottom, "differences": [],
           "details": {}}
    if len(per) >= 2:
        el_top = _campaign_elements(conn, top)
        el_bottom = _campaign_elements(conn, bottom)
        for label, key in (("hook_type", "hook_types"),
                           ("creator mode", "creator_modes"),
                           ("platform mix", "platforms")):
            a, b = el_top[key], el_bottom[key]
            if a != b:
                only_top = sorted(set(a) - set(b))
                only_bottom = sorted(set(b) - set(a))
                why["differences"].append(
                    "%s differs: %s has %s; %s has %s" % (
                        label, top, only_top or a or ["(none)"],
                        bottom, only_bottom or b or ["(none)"]))
            why["details"][key] = {"top": a, "bottom": b}
        st, sb = per[top]["spend"], per[bottom]["spend"]
        if st != sb:
            bigger = top if st > sb else bottom
            why["differences"].append(
                "scale differs: %s spent $%.2f vs %s $%.2f (%s carries more weight)"
                % (top, st, bottom, sb, bigger))
            why["details"]["spend"] = {"top": st, "bottom": sb}
        if not why["differences"]:
            why["differences"].append(
                "same elements on every axis: gap is execution/scale, not mix")
    return {"kpis": per, "ranking": ranking, "rank_by": rank_by, "why": why}


def build_report(conn, campaigns=None, kpis=("cpa", "ctr"), benchmark_sel=None,
                 fmt="one-pager"):
    """Generate a report over selected campaigns + KPIs + benchmark.

    fmt is "one-pager" (markdown), "csv", or "deck" (slide JSON).
    benchmark_sel may be None, a group_by string, a metric name, or a
    precomputed mapping.
    """
    fmt = (fmt or "one-pager").lower()
    if fmt not in ("one-pager", "csv", "deck"):
        raise ValueError("fmt must be one-pager, csv, or deck")
    wanted_kpis = [k for k in (kpis or []) if k in KPI_KEYS]
    if not wanted_kpis:
        raise ValueError("pick at least one KPI from %s" % sorted(KPI_KEYS))
    comp = compare_campaigns(conn, campaigns, rank_by=wanted_kpis[0])
    if benchmark_sel is None:
        bench = {}
    elif isinstance(benchmark_sel, str):
        bench = (benchmark(conn, benchmark_sel) if benchmark_sel in GROUPABLE
                 else benchmark_filtered(conn, {}, benchmark_sel).get("kpis", {}))
    elif isinstance(benchmark_sel, dict):
        bench = benchmark_sel
    else:
        raise ValueError("benchmark must be None, a group name, or a mapping")
    names = comp["ranking"]
    lines = ["# Campaign Report", "",
             "Campaigns: %s" % ", ".join(names),
             "KPIs: %s | Ranked by: %s" % (", ".join(wanted_kpis), comp["rank_by"]), ""]
    for name in names:
        row = comp["kpis"][name]
        lines.append("## %s" % name)
        for k in wanted_kpis:
            lines.append("- %s: %s" % (k.upper(), row[k]))
        lines.append("")
    lines += ["## Why %s leads %s (%s)" % (comp["why"]["top"], comp["why"]["bottom"],
                                           comp["why"]["metric"])]
    for d in comp["why"]["differences"]:
        lines.append("- %s" % d)
    lines += ["", "## Benchmark", ""]
    if isinstance(bench, dict) and bench:
        first = next(iter(bench.values()))
        if isinstance(first, dict) and "cpa" in first:
            for group, vals in bench.items():
                lines.append("- %s: CPA $%s, CTR %s, spend $%s"
                             % (group, vals.get("cpa"), vals.get("ctr"), vals.get("spend")))
        else:
            lines.append("- cohort: %s" % bench)
    else:
        lines.append("- (no benchmark selected)")
    markdown = "\n".join(lines)
    csv_lines = ["campaign," + ",".join(wanted_kpis)]
    for name in names:
        csv_lines.append(name + "," + ",".join(str(comp["kpis"][name][k])
                                               for k in wanted_kpis))
    csv_text = "\n".join(csv_lines) + "\n"
    deck = {"title": "Campaign Report", "rank_by": comp["rank_by"],
            "slides": [{"campaign": n, "kpis": {k: comp["kpis"][n][k] for k in wanted_kpis}}
                       for n in names],
            "why": comp["why"]["differences"], "benchmark": bench}
    if fmt == "csv":
        return {"format": "csv", "csv": csv_text, "markdown": markdown, "deck": deck}
    if fmt == "deck":
        return {"format": "deck", "deck": deck, "markdown": markdown, "csv": csv_text}
    return {"format": "one-pager", "markdown": markdown, "csv": csv_text, "deck": deck}

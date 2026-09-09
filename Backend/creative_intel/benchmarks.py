"""Spend-weighted benchmarks over the canonical ads dataset."""

import json

GROUPABLE = ("platform", "campaign", "hook_type", "creator_vs_branded")


def _weight(rows, metric):
    spend = sum(r["spend"] for r in rows)
    if spend <= 0:
        return 0.0
    return sum(r["spend"] * r[metric] for r in rows) / spend


def summarize(rows):
    """Spend-weighted roll-up of ad rows sharing one group key.

    Extended keys (clicks, conversions, video_views, cpm, vtr, roas)
    are additive: every pre-existing key keeps its exact meaning so
    older consumers and tests are unaffected.
    """
    spend = sum(r["spend"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    views = sum(r.get("video_views", 0) or 0 for r in rows)
    revenue = sum(r.get("revenue", 0) or 0 for r in rows)
    return {
        "n_ads": len(rows),
        "spend": round(spend, 2),
        "impressions": impr,
        "clicks": clicks,
        "conversions": conv,
        "video_views": views,
        "revenue": round(revenue, 2),
        "ctr": round(clicks / impr, 4) if impr else None,
        "cpc": round(spend / clicks, 2) if clicks else None,
        "cpm": round(spend / impr * 1000, 2) if impr else None,
        "vtr": round(views / impr, 4) if impr else None,
        "conv_rate_weighted": round(_weight(rows, "conv_rate"), 4),
        "cpa": round(spend / conv, 2) if conv else None,
        "roas": round(revenue / spend, 4) if spend else None,
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

FILTER_KEYS = ("vertical", "platform", "funnel", "objective", "market",
               "client", "date", "campaign")

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
        "cpm": round(spend / impr * 1000, 2) if impr else None,
        "vtr": round(views / impr, 4) if impr else None,
        "ctr": round(clicks / impr, 4) if impr else None,
        "cpc": round(spend / clicks, 2) if clicks else None,
        "cpa": round(spend / conv, 2) if conv else None,
        "roas": round(revenue / spend, 4) if spend else None,
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
    project = str(project_of(row) or "").lower()
    if filt.get("include_projects") and project not in [
            str(p).lower() for p in filt["include_projects"]]:
        return False
    if filt.get("exclude_projects") and project in [
            str(p).lower() for p in filt["exclude_projects"]]:
        return False
    return True


# ads-column behind each scope axis ("funnel" reads funnel_stage;
# "project" is matched Python-side via project_of, which falls back
# to campaign, so it is deliberately absent here).
SCOPE_COLUMNS = {"client": "client",
                 "campaign": "campaign", "platform": "platform",
                 "vertical": "vertical", "market": "market",
                 "funnel": "funnel_stage", "objective": "objective",
                 "date": "date"}


class Scope:
    """One reusable analysis scope for every analytics operation.

    Axes: client, project, campaign, platform, vertical, market,
    funnel, objective, date. "all"/blank means no constraint;
    matching is case-insensitive. campaign_kpis, creative rows,
    benchmark, compare_creatives, compare_campaigns, ask_data,
    build_report and retention patterns all take the same scope,
    so a Beauty + Spain + TikTok + Lower Funnel view can never
    silently analyse a broader dataset.
    """

    AXES = ("client", "project", "campaign", "platform", "vertical",
            "market", "funnel", "objective", "date")

    def __init__(self, raw=None):
        self.axes = {}
        for key in self.AXES:
            vals = _as_list((raw or {}).get(key))
            vals = [v for v in vals if v not in ("", "all")]
            if vals:
                self.axes[key] = sorted(set(vals))

    @classmethod
    def from_query(cls, query, ignore=()):
        """Build from a parse_qs query dict. "project" stays a
        project list (include_projects semantics live in
        normalized()); keys in ignore are skipped (the campaign
        compare route reuses ?campaign= for its candidate list)."""
        raw = {}
        for key in cls.AXES:
            if key in ignore:
                continue
            if key == "project":
                raw[key] = [v for v in query.get("project", [])
                            if v not in ("", "all")]
            else:
                raw[key] = [v for v in query.get(key, [])
                            if v not in ("", "all")]
        return cls(raw)

    @classmethod
    def from_payload(cls, payload):
        """Build from a POST body carrying a "filters" object."""
        return cls((payload or {}).get("filters") or {})

    def normalized(self):
        """normalize_filters-compatible dict for match_filters."""
        filt = {k: list(v) for k, v in self.axes.items() if k != "project"}
        if self.axes.get("project"):
            filt["include_projects"] = list(self.axes["project"])
        return normalize_filters(filt)

    def match(self, row):
        """True when an enriched ads row is inside this scope."""
        return match_filters(row, self.normalized())

    def sql(self):
        """Case-insensitive WHERE fragment over ads columns for
        direct SQL aggregations. Returns (clause, params); clause
        is "1=1" when the scope is empty. The project axis is
        skipped here (matched Python-side via project_of); callers
        doing pure-SQL aggregation must AND a project match with
        self.match or drop the axis explicitly."""
        bits, params = [], []
        for key in self.AXES:
            vals = self.axes.get(key)
            if not vals or key not in SCOPE_COLUMNS:
                continue
            col = SCOPE_COLUMNS[key]
            bits.append("(%s)" % " OR ".join(
                ["lower(%s)=lower(?)" % col] * len(vals)))
            params.extend(vals)
        if not bits:
            return "1=1", []
        return " AND ".join(bits), params

    def describe(self):
        """Short human label ("Beauty, Spain, TikTok") or "All data"."""
        bits = []
        for key in self.AXES:
            if self.axes.get(key):
                bits.append(", ".join(self.axes[key]))
        return "; ".join(bits) if bits else "All data"

    def is_empty(self):
        return not self.axes


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


def _campaign_elements(conn, campaign, scope=None):
    """Distinct creative elements behind one campaign (for why-analysis).

    scope (shared Scope or plain filter dict) restricts the rows, so
    a Market=Spain why-analysis never cites the French creative mix.
    """
    import json
    scope = scope if isinstance(scope, Scope) else Scope(scope)
    rows = [r for r in all_rows(conn)
            if (r.get("campaign") or "") == campaign and scope.match(r)]
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


def compare_campaigns(conn, campaigns=None, rank_by="cpa", filters=None):
    """Compare campaigns: per-campaign KPIs plus a why-analysis.

    rank_by picks the ranking metric (lower-is-better for cpm/cpa,
    higher-is-better for vtr/ctr/roas). filters is the shared
    analysis Scope (or a plain filter dict): only scoped rows feed
    the KPIs. The why-analysis names which elements (hook_type,
    creator mode, platform mix, scale) differ between the top- and
    bottom-ranked campaigns. When every candidate's rank_by KPI is
    uncomputable (None), there is no winner: top/bottom are None
    and the UI must read "Insufficient data / no winner" instead
    of crowning an arbitrary campaign.
    """
    if rank_by not in KPI_KEYS:
        raise ValueError("rank_by must be one of %s" % sorted(KPI_KEYS))
    scope = filters if isinstance(filters, Scope) else Scope(filters)
    per = campaign_kpis(conn, campaigns, filters=scope.normalized())
    if len(per) < 1:
        raise ValueError("no campaigns match %r" % (campaigns,))
    higher = KPI_DIRECTIONS[rank_by] == "higher"

    def _rank_key(name):
        # Uncomputable (None) always ranks last, never as a false zero.
        value = per[name][rank_by]
        if value is None:
            return (1, 0.0)
        return (0, -value if higher else value)

    ranking = sorted(per, key=_rank_key)
    if all(per[name][rank_by] is None for name in ranking):
        why = {"metric": rank_by, "top": None, "bottom": None,
               "differences": ["Insufficient data / no winner: %s is "
                               "uncomputable for every compared campaign."
                               % rank_by.upper()],
               "details": {}}
        return {"kpis": per, "ranking": ranking, "rank_by": rank_by,
                "why": why, "scope": scope.describe()}
    top, bottom = ranking[0], ranking[-1]
    why = {"metric": rank_by, "top": top, "bottom": bottom, "differences": [],
           "details": {}}
    if len(per) >= 2:
        el_top = _campaign_elements(conn, top, scope)
        el_bottom = _campaign_elements(conn, bottom, scope)
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
    return {"kpis": per, "ranking": ranking, "rank_by": rank_by,
            "why": why, "scope": scope.describe()}


def _span_min(ann, key):
    """Earliest start_s across a span list (brand/product/logo)."""
    spans = (ann or {}).get(key) or []
    starts = [s.get("start_s") for s in spans
              if isinstance(s, dict)
              and isinstance(s.get("start_s"), (int, float))
              and not isinstance(s.get("start_s"), bool)]
    return min(starts) if starts else None


def _creative_rows(conn, campaign, scope=None):
    """Per-creative performance + annotation labels for one campaign.

    scope (Scope or plain filter dict, default everything) restricts
    the ads rows feeding each creative's KPIs, so a creative used in
    Campaign A + B shows only Campaign-A metrics when the scope
    selects Campaign A. Rows also carry the full creative-analysis
    classification set the XLSX export needs.
    """
    scope = scope if isinstance(scope, Scope) else Scope(scope)
    cols = ["spend", "impressions", "clicks", "conversions",
            "video_views", "revenue", "platform", "client", "project",
            "campaign", "vertical", "market", "objective",
            "funnel_stage", "date"]
    out = []
    for (key,) in conn.execute(
            "SELECT DISTINCT creative_key FROM ads WHERE campaign=?",
            (campaign,)).fetchall():
        rows = [dict(zip(cols, r)) for r in conn.execute(
            "SELECT %s FROM ads WHERE creative_key=? AND campaign=?" % (
                ", ".join(cols)), (key, campaign,)).fetchall()]
        rows = [r for r in rows if scope.match(r)]
        if not rows and not scope.is_empty():
            continue
        spend = sum(r["spend"] for r in rows)
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        conv = sum(r["conversions"] for r in rows)
        views = sum(r["video_views"] or 0 for r in rows)
        revenue = sum(r["revenue"] or 0 for r in rows)
        platforms = sorted({r["platform"] for r in rows if r["platform"]})

        def _distinct(col):
            return sorted({str(r[col]) for r in rows if r[col]})
        got = conn.execute("SELECT annotation_json FROM annotations"
                           " WHERE creative_key=?", (key,)).fetchone()
        try:
            ann = json.loads(got[0]) if got else {}
        except ValueError:
            ann = {}
        ann = ann or {}
        status = conn.execute("SELECT status FROM creatives WHERE creative_key=?",
                              (key,)).fetchone()
        duration = conn.execute("SELECT duration_s FROM creatives WHERE creative_key=?",
                                (key,)).fetchone()
        struct = ann.get("structure") or {}
        slots = sorted(s for s, seg in struct.items()
                       if isinstance(seg, dict)
                       and (seg.get("end_s") or 0) > (seg.get("start_s") or 0))
        cta = ann.get("cta")
        if isinstance(cta, dict):
            cta_text = ("set %ss-%ss" % (cta.get("start_s"),
                                         cta.get("end_s"))
                        if (cta.get("end_s") or 0) > (cta.get("start_s") or 0)
                        else "")
        else:
            cta_text = str(cta or "")
        out.append({
            "creative_key": key,
            "platform": ",".join(platforms),
            "spend": round(spend, 2),
            "impressions": impr,
            "clicks": clicks,
            "conversions": conv,
            "video_views": views,
            "revenue": round(revenue, 2),
            "cpm": round(spend / impr * 1000, 2) if impr else None,
            "vtr": round(views / impr, 4) if impr else None,
            "ctr": round(clicks / impr, 4) if impr else None,
            "cpc": round(spend / clicks, 2) if clicks else None,
            "cpa": round(spend / conv, 2) if conv else None,
            "roas": round(revenue / spend, 4) if spend else None,
            "hook_type": ann.get("hook_type") or "unannotated",
            "hook_modality": ann.get("hook_modality") or "unknown",
            "creator_vs_branded": ann.get("creator_vs_branded") or "unannotated",
            "duration_s": ann.get("duration_s") or (duration[0] if duration else 0),
            "status": ann.get("status") or (status[0] if status else "auto"),
            "verified": ann.get("status") == "human_verified",
            "client": "; ".join(_distinct("client")),
            "project": "; ".join(_distinct("project")),
            "vertical": "; ".join(_distinct("vertical")),
            "market": "; ".join(_distinct("market")),
            "funnel": "; ".join(_distinct("funnel_stage")),
            "objective": "; ".join(_distinct("objective")),
            "date": "; ".join(_distinct("date")),
            "brand_first_visible_s": _span_min(ann, "brand_seconds"),
            "product_first_visible_s": _span_min(ann, "product_seconds"),
            "logo_first_visible_s": _span_min(ann, "logo_seconds"),
            "brand_audio_mention_s": ann.get("brand_audio_mention_s"),
            "brand_audio_approx": bool(ann.get("brand_audio_approx")),
            "cta": cta_text,
            "supers": "; ".join(str(s) for s in (ann.get("supers") or [])
                                if s),
            "voiceover": "voiceover" in slots,
            "editing_pace_cuts_per_min": ann.get("pace_cuts_per_min"),
            "structure": ", ".join(slots),
        })
    return out


def _report_extras(conn, names, strict_human=False, scope=None,
                   rank_by="cpa"):
    """Best/worst creatives, hook learnings, heuristic next steps.

    Everything is computed from uploaded rows + annotations in this
    call. scope (shared Scope or plain filter dict) restricts every
    creative row, so a report on Beauty + Spain never blends in
    France rows. rank_by (a KPI_KEYS metric) picks the contention
    metric with its correct higher/lower direction: a ROAS report
    crowns ROAS leaders, never CPA leaders. Uncomputable-for-all
    metrics yield no best/watch rather than an arbitrary pick.
    Recommendations are plainly labelled heuristic: they rank by
    the measured rank_by metric, they do not invent diagnoses.
    In strict mode best/watch contention is limited to
    HUMAN-VERIFIED annotations so no unverified hook/format label
    can enter an official report.
    """
    if rank_by not in KPI_KEYS:
        raise ValueError("rank_by must be one of %s" % sorted(KPI_KEYS))
    higher = KPI_DIRECTIONS[rank_by] == "higher"
    scope = scope if isinstance(scope, Scope) else Scope(scope)
    per_campaign = {}
    hook_spend, hook_conv = {}, {}
    strict_nulled = 0
    for name in names:
        rows = _creative_rows(conn, name, scope=scope)

        def _rank(pool):
            def _key(r):
                # Uncomputable (None) always ranks last, never as a
                # false zero.
                value = r[rank_by]
                if value is None:
                    return (1, 0.0)
                return (0, -value if higher else value)
            ranked = sorted(pool, key=_key)
            if not ranked or ranked[0][rank_by] is None:
                return None, None
            return (ranked[0],
                    ranked[-1] if len(ranked) > 1 else None)

        best, worst = _rank(rows)
        if strict_human:
            # Verified-only contention: unverified hook/format labels
            # must not enter an official strict report.
            vbest, vworst = _rank([r for r in rows if r["verified"]])
            strict_nulled += ((best is not None and vbest is None) +
                              (worst is not None and vworst is None))
            best, worst = vbest, vworst
        per_campaign[name] = {
            "best": best,
            "worst": worst,
            "creatives": rows,
        }
        for r in rows:
            hook_spend[r["hook_type"]] = hook_spend.get(r["hook_type"], 0) + r["spend"]
            hook_conv[r["hook_type"]] = hook_conv.get(r["hook_type"], 0) + (
                r["conversions"] or 0)
    learnings = []
    if hook_spend:
        top_hook = max(hook_spend, key=lambda h: hook_spend[h])
        conv = hook_conv.get(top_hook, 0)
        hooked = [r for name in names for r in per_campaign[name]["creatives"]
                  if r["hook_type"] == top_hook]
        learnings.append((
            "%s hooks carry the most spend ($%s%s)." % (
                top_hook, f"{hook_spend[top_hook]:,.2f}",
                ", %s conversions" % conv if conv else ", no conversions yet"),
            all(r["verified"] for r in hooked) if hooked else True))
    unannotated = sum(1 for name in names for r in per_campaign[name]["creatives"]
                      if r["hook_type"] == "unannotated")
    if unannotated:
        learnings.append((
            "%d of %d creatives lack hook labels — annotate them to "
            "unlock hook learnings." % (
                unannotated, sum(len(per_campaign[n]["creatives"]) for n in names)),
            True))
    recommendations = []
    money = rank_by in ("cpm", "cpc", "cpa")
    sym = "$" if money else ""

    def _show_rank(value):
        return "n/a" if value is None else "%s%s" % (sym, value)

    contenders = [(n, per_campaign[n]["best"]) for n in names
                  if per_campaign[n]["best"] and
                  per_campaign[n]["best"][rank_by] is not None]
    if contenders:
        pick = (max if higher else min)
        top = pick(contenders, key=lambda kv: kv[1][rank_by])
        recommendations.append((
            "Scale candidate (heuristic): %s — %s best-creative %s "
            "at %s (%s)." % (
                top[0],
                "highest" if higher else "lowest", rank_by.upper(),
                _show_rank(top[1][rank_by]), top[1]["creative_key"]),
            bool(top[1]["verified"])))
        bottom = (min if higher else max)(
            contenders, key=lambda kv: kv[1][rank_by])
        if bottom[0] != top[0]:
            recommendations.append((
                "Watch (heuristic): %s — %s best-creative %s at %s. "
                "Compare its hook/format against %s before adding spend."
                % (bottom[0],
                   "lowest" if higher else "highest", rank_by.upper(),
                   _show_rank(bottom[1][rank_by]), top[0]),
                bool(bottom[1]["verified"] and top[1]["verified"])))
    if not recommendations:
        recommendations.append((
            "No %s values to rank yet — collect delivery data before "
            "scaling anything." % rank_by.upper(), True))
    return {"per_campaign": per_campaign,
            "learnings": [t for t, _v in learnings],
            "learnings_verified": [v for _t, v in learnings],
            "recommendations": [t for t, _v in recommendations],
            "recommendations_verified": [v for _t, v in recommendations],
            "strict_nulled": strict_nulled}


def _show(value):
    """Report rendering: uncomputable KPIs read n/a, never None/zero."""
    return "n/a" if value is None else value


def build_report(conn, campaigns=None, kpis=("cpa", "ctr"), benchmark_sel=None,
                 fmt="one-pager", strict_human=False, filters=None,
                 benchmark_scope="filters"):
    """Generate a report over selected campaigns + KPIs + benchmark.

    fmt is "one-pager" (markdown), "csv", "deck" (slide JSON),
    "pptx" (true PowerPoint bytes, base64), or "xlsx" (true
    spreadsheet bytes, base64). Binary formats ride inside the same
    JSON envelope so the local-first HTTP contract is unchanged.
    benchmark_sel may be None, a group_by string, a metric name, or a
    precomputed mapping. filters is the shared analysis Scope (or a
    plain filter dict): campaign KPIs, creative rows and the why
    analysis all read the identical scoped population, and the scope
    is printed on the report so a filtered export can never be
    mistaken for a full-dataset one. benchmark_scope is "filters"
    (default: the selected benchmark is computed over the same
    scope, labelled as such) or "global" (explicit opt-out: the
    benchmark reads the whole dataset and is labelled global).
    """
    fmt = (fmt or "one-pager").lower()
    if fmt not in ("one-pager", "csv", "deck", "pptx", "xlsx"):
        raise ValueError("fmt must be one-pager, csv, deck, pptx, or xlsx")
    report_kpis = KPI_KEYS + ("spend", "impressions", "clicks",
                             "conversions", "cpc")
    wanted_kpis = [k for k in (kpis or []) if k in report_kpis]
    if not wanted_kpis:
        raise ValueError("pick at least one KPI from %s" % sorted(report_kpis))
    rank_by = wanted_kpis[0] if wanted_kpis[0] in KPI_KEYS else "cpa"
    scope = filters if isinstance(filters, Scope) else Scope(filters)
    comp = compare_campaigns(conn, campaigns, rank_by=rank_by,
                             filters=scope)
    bench_scoped = (benchmark_scope or "filters").lower() != "global"
    bench_filt = scope.normalized() if bench_scoped else None
    bench_label = ("scoped (%s)" % scope.describe() if bench_scoped
                   else "global (whole dataset)")
    if benchmark_sel is None:
        bench = {}
    elif isinstance(benchmark_sel, str):
        bench = (benchmark(conn, benchmark_sel, filters=bench_filt)
                 if benchmark_sel in GROUPABLE
                 else benchmark_filtered(
                     conn, bench_filt or {}, benchmark_sel).get("kpis", {}))
    elif isinstance(benchmark_sel, dict):
        bench = benchmark_sel
    else:
        raise ValueError("benchmark must be None, a group name, or a mapping")
    names = comp["ranking"]
    lines = ["# Campaign Report", "",
             "Scope: %s" % scope.describe(),
             "Campaigns: %s" % ", ".join(names),
             "KPIs: %s | Ranked by: %s" % (", ".join(wanted_kpis), comp["rank_by"]), ""]
    for name in names:
        row = comp["kpis"][name]
        lines.append("## %s" % name)
        for k in wanted_kpis:
            lines.append("- %s: %s" % (k.upper(), _show(row[k])))
        lines.append("")
    if comp["why"]["top"] is None:
        lines += ["## No winner (%s uncomputable for every campaign — "
                  "insufficient data, no arbitrary pick)"
                  % comp["why"]["metric"].upper()]
    else:
        lines += ["## Why %s leads %s (%s)" % (
            comp["why"]["top"], comp["why"]["bottom"],
            comp["why"]["metric"])]
    for d in comp["why"]["differences"]:
        lines.append("- %s" % d)
    lines += ["", "## Benchmark (%s)" % bench_label, ""]
    if isinstance(bench, dict) and bench:
        first = next(iter(bench.values()))
        if isinstance(first, dict) and "cpa" in first:
            for group, vals in bench.items():
                lines.append("- %s: CPA $%s, CTR %s, spend $%s"
                             % (group, _show(vals.get("cpa")),
                                _show(vals.get("ctr")), vals.get("spend")))
        else:
            lines.append("- cohort: %s" % bench)
    else:
        lines.append("- (no benchmark selected)")
    strict = bool(strict_human)
    extras = _report_extras(conn, names, strict_human=strict,
                            scope=scope, rank_by=rank_by)
    rank_sym = "$" if rank_by in ("cpm", "cpc", "cpa") else ""

    def _show_rank(value):
        return "n/a" if value is None else "%s%s" % (rank_sym, value)
    unverified_excluded = 0
    if strict:
        # HUMAN-VERIFIED parity: insights resting on unverified
        # annotations are dropped (counted), never silently kept.
        kept_learn = [(t, v) for t, v in zip(
            extras["learnings"], extras["learnings_verified"]) if v]
        kept_reco = [(t, v) for t, v in zip(
            extras["recommendations"],
            extras["recommendations_verified"]) if v]
        unverified_excluded = (
            (len(extras["learnings"]) - len(kept_learn)) +
            (len(extras["recommendations"]) - len(kept_reco)) +
            extras.get("strict_nulled", 0))
        extras = dict(
            extras,
            learnings=[t for t, _v in kept_learn] or [
                "No HUMAN-VERIFIED learnings yet."],
            learnings_verified=[True] * (len(kept_learn) or 1),
            recommendations=[t for t, _v in kept_reco] or [
                "No HUMAN-VERIFIED recommendations yet."],
            recommendations_verified=[True] * (len(kept_reco) or 1))
    lines += ["", "## Best / watch creatives", ""]
    for name in names:
        best = extras["per_campaign"][name]["best"]
        worst = extras["per_campaign"][name]["worst"]
        if best:
            lines.append("- %s best: %s (%s %s | CPA $%s, CTR %s, %s / %s)" % (
                name, best["creative_key"], comp["rank_by"].upper(),
                _show_rank(best[comp["rank_by"]]),
                _show(best["cpa"]), _show(best["ctr"]),
                best["hook_type"], best["creator_vs_branded"]))
        if worst:
            lines.append("- %s watch: %s (%s %s | CPA $%s, CTR %s, %s / %s)" % (
                name, worst["creative_key"], comp["rank_by"].upper(),
                _show_rank(worst[comp["rank_by"]]),
                _show(worst["cpa"]), _show(worst["ctr"]),
                worst["hook_type"], worst["creator_vs_branded"]))
    lines += ["", "## Creative learnings", ""]
    lines += ["- %s" % l for l in extras["learnings"]] or ["- —"]
    lines += ["", "## Recommendations / next steps (heuristic)", ""]
    lines += ["- %s" % r for r in extras["recommendations"]]
    markdown = "\n".join(lines)
    csv_lines = ["campaign," + ",".join(wanted_kpis)]
    for name in names:
        csv_lines.append(name + "," + ",".join(
            "" if comp["kpis"][name][k] is None
            else str(comp["kpis"][name][k]) for k in wanted_kpis))
    csv_text = "\n".join(csv_lines) + "\n"
    deck = {"title": "Campaign Report", "scope": scope.describe(),
            "benchmark_scope": bench_label,
            "rank_by": comp["rank_by"],
            "slides": [{"campaign": n, "kpis": {k: comp["kpis"][n][k] for k in wanted_kpis}}
                       for n in names],
            "why": comp["why"]["differences"], "benchmark": bench,
            "creatives": {n: {"best": extras["per_campaign"][n]["best"],
                              "worst": extras["per_campaign"][n]["worst"]}
                          for n in names},
            "learnings": extras["learnings"],
            "learnings_verified": extras["learnings_verified"],
            "recommendations": extras["recommendations"],
            "recommendations_verified": extras["recommendations_verified"],
            "strict_human": strict,
            "unverified_excluded": unverified_excluded}
    if fmt == "csv":
        return {"format": "csv", "csv": csv_text, "markdown": markdown, "deck": deck}
    if fmt == "deck":
        return {"format": "deck", "deck": deck, "markdown": markdown, "csv": csv_text}
    if fmt in ("pptx", "xlsx"):
        import base64
        from creative_intel import ooxml
        if fmt == "pptx":
            slides = [{"title": "Campaign Report — %s" % comp["rank_by"].upper(),
                       "bullets": ["Campaigns: %s" % ", ".join(names),
                                   "KPIs: %s" % ", ".join(wanted_kpis)]}]
            for name in names:
                row = comp["kpis"][name]
                bullets = ["%s: %s" % (k.upper(), _show(row[k]))
                           for k in wanted_kpis]
                best = deck["creatives"][name]["best"]
                worst = deck["creatives"][name]["worst"]
                if best:
                    bullets.append("Best creative: %s (%s %s | CPA $%s, %s / %s)" % (
                        best["creative_key"], comp["rank_by"].upper(),
                        _show_rank(best[comp["rank_by"]]),
                        _show(best["cpa"]),
                        best["hook_type"], best["creator_vs_branded"]))
                if worst:
                    bullets.append("Watch: %s (%s %s | CPA $%s, %s / %s)" % (
                        worst["creative_key"], comp["rank_by"].upper(),
                        _show_rank(worst[comp["rank_by"]]),
                        _show(worst["cpa"]),
                        worst["hook_type"], worst["creator_vs_branded"]))
                slides.append({"title": name, "bullets": bullets})
            why_title = ("Why %s leads" % comp["why"]["top"]
                         if comp["why"]["top"] is not None
                         else "No winner — insufficient data")
            slides.append({"title": why_title,
                           "bullets": comp["why"]["differences"] or ["—"]})
            bench = deck.get("benchmark") or {}
            bench_bullets = []
            if isinstance(bench, dict) and bench:
                first = next(iter(bench.values()))
                if isinstance(first, dict) and "cpa" in first:
                    for group, vals in bench.items():
                        bench_bullets.append(
                            "%s: CPA $%s, CTR %s, spend $%s" % (
                                group, _show(vals.get("cpa")),
                                _show(vals.get("ctr")), vals.get("spend")))
                else:
                    bench_bullets.append("Cohort: %s" % str(bench)[:300])
            else:
                bench_bullets.append("(no benchmark selected)")
            slides.append({"title": "Benchmarks", "bullets": bench_bullets})
            slides.append({"title": "Creative learnings",
                           "bullets": deck["learnings"] or ["—"]})
            slides.append({"title": "Recommendations / next steps",
                           "bullets": deck["recommendations"] or ["—"]})
            blob = ooxml.build_pptx("Campaign Report", slides)
            return {"format": "pptx", "filename": "campaign-report.pptx",
                    "pptx_b64": base64.b64encode(blob).decode(),
                    "markdown": markdown, "csv": csv_text, "deck": deck}
        sheet = {"name": "Campaigns",
                 "header": ["campaign"] + wanted_kpis,
                 "rows": [[name] + [comp["kpis"][name][k] for k in wanted_kpis]
                          for name in names]}
        why = {"name": "Why analysis",
               "header": ["finding"],
               "rows": [[d] for d in comp["why"]["differences"]] or [["—"]]}
        creatives = {"name": "Creatives",
                     "header": ["campaign", "role", "creative", "spend",
                                "ctr", "cpa", "hook", "format"],
                     "rows": [[name, role,
                               (slot or {}).get("creative_key"),
                               (slot or {}).get("spend"),
                               (slot or {}).get("ctr"),
                               (slot or {}).get("cpa"),
                               (slot or {}).get("hook_type"),
                               (slot or {}).get("creator_vs_branded")]
                              for name in names
                              for role, slot in (
                                  ("best", deck["creatives"][name]["best"]),
                                  ("watch", deck["creatives"][name]["worst"]))
                              if slot]}
        learn = {"name": "Learnings",
                 "header": ["finding", "human_verified"],
                 "rows": [[l, v] for l, v in zip(
                     deck["learnings"], deck["learnings_verified"])] or [["—", ""]]}
        reco = {"name": "Next steps",
                "header": ["recommendation (heuristic)", "human_verified"],
                "rows": [[r, v] for r, v in zip(
                    deck["recommendations"],
                    deck["recommendations_verified"])] or [["—", ""]]}
        # Every creative, every performance number and every
        # creative-analysis classification: the workbook must stand
        # alone without re-querying the app.
        all_header = ["client", "project", "campaign", "platform",
                      "vertical", "market", "funnel", "objective",
                      "date", "creative", "spend", "impressions",
                      "clicks", "conversions", "video_views", "revenue",
                      "cpm", "vtr", "ctr", "cpc", "cpa", "roas",
                      "hook_type", "hook_modality", "creator_vs_branded",
                      "duration_s", "brand_first_visible_s",
                      "product_first_visible_s", "logo_first_visible_s",
                      "brand_audio_mention_s", "brand_audio_approx",
                      "cta", "supers", "voiceover",
                      "editing_pace_cuts_per_min", "structure",
                      "status", "human_verified"]
        all_creatives = {
            "name": "All Creatives",
            "header": all_header,
            "rows": [[r["client"], r["project"], name, r["platform"],
                      r["vertical"], r["market"], r["funnel"],
                      r["objective"], r["date"], r["creative_key"],
                      r["spend"], r["impressions"], r["clicks"],
                      r["conversions"], r["video_views"], r["revenue"],
                      r["cpm"], r["vtr"], r["ctr"], r["cpc"], r["cpa"],
                      r["roas"], r["hook_type"], r["hook_modality"],
                      r["creator_vs_branded"], r["duration_s"],
                      r["brand_first_visible_s"],
                      r["product_first_visible_s"],
                      r["logo_first_visible_s"],
                      r["brand_audio_mention_s"],
                      r["brand_audio_approx"], r["cta"], r["supers"],
                      r["voiceover"],
                      r["editing_pace_cuts_per_min"], r["structure"],
                      r["status"], r["verified"]]
                     for name in names
                     for r in extras["per_campaign"][name]["creatives"]]}
        bench = deck.get("benchmark") or {}
        if isinstance(bench, dict) and bench and isinstance(
                next(iter(bench.values())), dict):
            bsheet = {"name": "Benchmarks",
                      "header": ["group", "cpa", "ctr", "spend"],
                      "rows": [[g, v.get("cpa"), v.get("ctr"), v.get("spend")]
                               for g, v in bench.items()]}
        else:
            bsheet = {"name": "Benchmarks", "header": ["benchmark"],
                      "rows": [[str(bench)[:300] if bench
                                else "(no benchmark selected)"]]}
        # Raw canonical imported rows (scoped): the workbook carries
        # full performance data, not only summaries.
        raw_cols = [c[0] for c in conn.execute(
            "SELECT * FROM ads LIMIT 0").description]
        raw_all = [dict(zip(raw_cols, v)) for v in conn.execute(
            "SELECT * FROM ads").fetchall()]
        raw_rows = [[r.get(c) for c in raw_cols if c != "id"]
                    for r in raw_all if scope.match(r)]
        raw_header = [c for c in raw_cols if c != "id"] + ["scope"]
        raw = {"name": "Raw Performance Data",
               "header": raw_header,
               "rows": [row + [scope.describe()] for row in raw_rows]
               or [[None] * len(raw_header)]}
        blob = ooxml.build_xlsx([sheet, why, creatives, all_creatives,
                                 raw, bsheet, learn, reco])
        return {"format": "xlsx", "filename": "campaign-report.xlsx",
                "xlsx_b64": base64.b64encode(blob).decode(),
                "markdown": markdown, "csv": csv_text, "deck": deck}
    return {"format": "one-pager", "markdown": markdown, "csv": csv_text, "deck": deck}

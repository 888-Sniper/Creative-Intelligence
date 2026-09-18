"""Shared product logic: analytics actions used by every server shell.

Moved verbatim from the legacy stdlib server so the FastAPI app and
any remaining callers run identical logic. No HTTP or auth here.
"""

from __future__ import annotations

import json
import os
import sqlite3

from creative_intel import (
    creative,
    demo_art,
    export_gate,
    ingest,
    media,
    providers,
    replay,
    schema,
    sync,
)

BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
WEB_INDEX = os.path.normpath(os.path.join(BASE, "Web", "Index.html"))
ASSETS_DIR = os.path.normpath(os.path.join(BASE, "Web", "assets"))
# React production build (item 51: `pnpm build` in
# apps/creative-intelligence-ui). Served at / when present; the legacy
# static shell above remains the fallback so fresh checkouts and
# build-less environments keep working unchanged.
REACT_DIST_DIR = os.path.normpath(
    os.path.join(BASE, "apps", "creative-intelligence-ui", "dist"))
REACT_INDEX = os.path.join(REACT_DIST_DIR, "index.html")
REACT_ASSETS_DIR = os.path.join(REACT_DIST_DIR, "assets")


def react_index() -> str:
    """Production frontend entry: React build when built, else legacy."""
    if os.path.isfile(REACT_INDEX):
        return REACT_INDEX
    return WEB_INDEX


def _fixture_dir():
    for name in ("fixtures", "Fixtures"):
        candidate = os.path.join(BASE, name)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(BASE, "fixtures")


FIXTURES = _fixture_dir()


FILTER_AXES = ("platform", "vertical", "funnel", "objective",
               "market", "client", "date")

VIEW_KPIS = ("all", "spend", "ctr", "cpc", "cpa", "cpm", "vtr",
             "roas")

VIEW_RANKS = ("cpa", "cpm", "ctr", "vtr", "roas")

VIEW_KEYS = ("filters", "kpi", "view", "benchmark", "benchmark_scope",
             "rank_by", "compare_mode")


def connect(db_path):
    conn = sqlite3.connect(db_path)
    schema.init_db(conn)
    return conn


def _filters_from_query(query):
    """Canonical dimension filters from URL query params.

    Multi-values per axis allowed (?vertical=Beauty&vertical=Food).
    "all" and blanks mean no constraint. "project" maps to the
    include_projects list (project identity falls back to campaign).
    """
    out = {}
    for axis in FILTER_AXES:
        vals = [v for v in query.get(axis, []) if v not in ("", "all")]
        if vals:
            out[axis] = vals
    projects = [v for v in query.get("project", []) if v not in ("", "all")]
    if projects:
        out["include_projects"] = projects
    return out


def _media_dir(explicit=None):
    if explicit:
        os.makedirs(explicit, exist_ok=True)
        return explicit
    env = os.environ.get("CREATIVE_INTEL_MEDIA_DIR")
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    return media.media_dir(BASE)


def _span_start(ann, key):
    spans = (ann or {}).get(key) or []
    starts = [s.get("start_s") for s in spans
              if isinstance(s, dict)
              and isinstance(s.get("start_s"), (int, float))
              and not isinstance(s.get("start_s"), bool)]
    return min(starts) if starts else None


def _slot_set(ann, slot):
    seg = ((ann or {}).get("structure") or {}).get(slot) or {}
    try:
        return float(seg.get("end_s", 0)) > float(seg.get("start_s", 0))
    except (TypeError, ValueError):
        return False


def _creative_why(a, b, da, db):
    """Data-grounded pairwise notes: measured deltas plus observed
    annotation contrast across every creative dimension. Never causal
    claims, never invented data."""
    if not a or not b:
        return {"top": None, "differences": ["Pick two creatives to compare."]}
    diffs = []
    for metric, higher_wins in (("cpa", False), ("ctr", True), ("vtr", True),
                                ("cpc", False), ("cpm", False), ("roas", True)):
        # Missing is missing: a None KPI (e.g. CPA with no conversions)
        # must never coerce to 0, which would make an unmeasured
        # lower-is-better metric look unbeatable.
        va, vb = da.get(metric), db.get(metric)
        if va is None or vb is None:
            if (va is None) != (vb is None):
                diffs.append(
                    "%s is not measurable for %s (insufficient data)"
                    % (metric.upper(), a if va is None else b))
            continue
        if va == vb:
            continue
        winner = a if (va > vb) == higher_wins else b
        diffs.append("%s leads %s on %s (%s vs %s)"
                     % (winner, b if winner == a else a,
                        metric.upper(), va, vb))
    aa, ab = da.get("annotation") or {}, db.get("annotation") or {}
    for field, label in (("hook_type", "hook"), ("creator_vs_branded", "format"),
                           ("edit_style", "style")):
        fa, fb = aa.get(field), ab.get(field)
        if fa and fb and fa != fb:
            diffs.append("%s uses %s %s while %s uses %s"
                         % (a, label, fa, b, fb))
    dura, durb = aa.get("duration_s"), ab.get("duration_s")
    if dura and durb and dura != durb:
        diffs.append("Length: %s runs %ss vs %s at %ss."
                     % (a, dura, b, durb))
    for key, label in (("brand_seconds", "Brand"), ("product_seconds", "Product")):
        sa, sb = _span_start(aa, key), _span_start(ab, key)
        if sa is not None and sb is not None and sa != sb:
            diffs.append("%s appears at %ss in %s vs %ss in %s."
                         % (label, sa, a, sb, b))
        elif (sa is None) != (sb is None):
            shown = a if sa is not None else b
            diffs.append("%s appears in %s but has no timing in %s."
                         % (label, shown, b if shown == a else a))
    cta_a = aa.get("cta") or (_slot_set(aa, "cta") and "set")
    cta_b = ab.get("cta") or (_slot_set(ab, "cta") and "set")
    if bool(cta_a) != bool(cta_b):
        diffs.append("CTA is annotated in %s but not in %s."
                     % (a if cta_a else b, b if cta_a else a))
    sup_a, sup_b = aa.get("supers"), ab.get("supers")
    if bool(sup_a) != bool(sup_b):
        diffs.append("On-screen supers are annotated in %s but not in %s."
                     % (a if sup_a else b, b if sup_a else a))
    vo_a, vo_b = _slot_set(aa, "voiceover"), _slot_set(ab, "voiceover")
    if vo_a != vo_b:
        diffs.append("Voiceover is annotated in %s but not in %s."
                     % (a if vo_a else b, b if vo_a else a))
    struct_a = sorted(s for s in
                      ((aa.get("structure") or {}).keys()) if _slot_set(aa, s))
    struct_b = sorted(s for s in
                      ((ab.get("structure") or {}).keys()) if _slot_set(ab, s))
    if struct_a != struct_b:
        only_a = [s for s in struct_a if s not in struct_b]
        only_b = [s for s in struct_b if s not in struct_a]
        bits = []
        if only_a:
            bits.append("%s has %s" % (a, ", ".join(only_a)))
        if only_b:
            bits.append("%s has %s" % (b, ", ".join(only_b)))
        if bits:
            diffs.append("Structure: %s." % "; ".join(bits))
    top = None
    if (da.get("conversions") or 0) > 0 and (db.get("conversions") or 0) > 0:
        cpa_a, cpa_b = da.get("cpa"), db.get("cpa")
        if cpa_a is not None and cpa_b is not None:
            top = a if cpa_a <= cpa_b else b
    elif (da.get("impressions") or 0) > 0 or (db.get("impressions") or 0) > 0:
        top = a if (da.get("ctr", 0) or 0) >= (db.get("ctr", 0) or 0) else b
    if top is None:
        diffs.append("Neither creative has delivery data yet.")
    return {"top": top, "differences": diffs or ["No measurable difference."]}


def _multi_why(keys, datas):
    """Data-grounded N-way notes (3-6 creatives): per-metric leaders
    plus observed annotation contrast. Measured deltas only, never
    causal claims, never invented data."""
    keys = [k for k in keys if k]
    if len(keys) < 2:
        return {"top": None,
                "differences": ["Pick two or more creatives to compare."]}
    diffs = []
    for metric, higher_wins in (("cpa", False), ("cpc", False),
                                ("cpm", False), ("ctr", True),
                                ("vtr", True), ("roas", True)):
        valued = [(k, datas.get(k, {}).get(metric)) for k in keys]
        valued = [(k, v) for k, v in valued if v is not None]
        if len({v for _k, v in valued}) < 2:
            continue
        best = (max if higher_wins else min)(valued, key=lambda kv: kv[1])
        diffs.append("%s leads on %s (%s vs %s)" % (
            best[0], metric.upper(), best[1],
            ", ".join("%s %s" % (k, v) for k, v in valued if k != best[0])))
    anns = {k: (datas.get(k, {}).get("annotation") or {}) for k in keys}
    for field, label in (("hook_type", "Hook"), ("hook_modality", "Modality"),
                         ("creator_vs_branded", "Format"),
                         ("edit_style", "Style")):
        vals = sorted({a.get(field) for a in anns.values() if a.get(field)})
        if len(vals) > 1:
            diffs.append("%s varies: %s." % (
                label, "; ".join("%s=%s" % (k, anns[k].get(field) or "—")
                                 for k in keys)))
    durs = sorted({a.get("duration_s") for a in anns.values()
                   if a.get("duration_s")})
    if len(durs) > 1:
        diffs.append("Length varies: %s." % "; ".join(
            "%s=%ss" % (k, anns[k].get("duration_s")) for k in keys
            if anns[k].get("duration_s")))
    for key, label in (("brand_seconds", "Brand"), ("product_seconds", "Product")):
        timed = sorted({k for k in keys if _span_start(anns[k], key) is not None})
        if timed and len(timed) != len(keys):
            diffs.append("%s timing is annotated in %s but not in %s." % (
                label, ", ".join(timed),
                ", ".join(k for k in keys if k not in timed)))
    cta = sorted({k for k in keys if anns[k].get("cta")})
    if cta and len(cta) != len(keys):
        diffs.append("CTA is annotated in %s but not in %s." % (
            ", ".join(cta), ", ".join(k for k in keys if k not in cta)))
    converting = [k for k in keys if (datas.get(k, {}).get("conversions") or 0) > 0]
    top = None
    if converting:
        ranked = [(k, datas[k].get("cpa")) for k in converting
                  if datas.get(k, {}).get("cpa") is not None]
        if ranked:
            top = min(ranked, key=lambda kv: kv[1])[0]
    else:
        shown = [(k, datas.get(k, {}).get("ctr")) for k in keys]
        shown = [(k, v) for k, v in shown if v is not None]
        if shown:
            top = max(shown, key=lambda kv: kv[1])[0]
    if top is None:
        diffs.append("Neither creative has delivery data yet.")
    return {"top": top, "differences": diffs or ["No measurable difference."]}


def save_view(conn, name, state):
    """Persist a named analysis view (filters + KPI + tab + benchmark
    + report rank).

    state carries the exact UI snapshot: filters (scope axes),
    kpi (sort selector), view (active tab), benchmark (report
    group-by), benchmark_scope (filters|global). Unknown keys or
    axes are rejected; saving an existing name replaces it so
    re-saving an updated view never duplicates. Returns the stored
    record with its id.
    """
    from creative_intel import benchmarks as _bench
    name = str(name or "").strip()
    if not name or len(name) > 80:
        raise ValueError("view needs a name of 1-80 characters")
    if not isinstance(state, dict):
        raise ValueError("view state must be an object")
    unknown = sorted(set(state) - set(VIEW_KEYS))
    if unknown:
        raise ValueError("unknown view keys: %s" % unknown)
    clean = {}
    if "filters" in state:
        if not isinstance(state["filters"], dict):
            raise ValueError("view filters must be an object")
        # "creative" is a client-restored explicit creative-key list
        # (compare deep-link), not a Scope axis: accepted and stored
        # verbatim, never fed into server-side scoping.
        unknown_axes = sorted(
            set(state["filters"]) - set(_bench.Scope.AXES) - {"creative"})
        if unknown_axes:
            raise ValueError("unknown view filter axes: %s" % unknown_axes)
        _bench.Scope({k: v for k, v in state["filters"].items()
                       if k not in ("status", "spend_min", "spend_max")}
                      ).normalized()  # validates row-level values
        _bench.Scope(state["filters"]).campaign_axes()  # validates status/spend
        clean["filters"] = {k: v for k, v in state["filters"].items()
                            if v not in ("", "all", [], {})}
    if "kpi" in state:
        if state["kpi"] not in VIEW_KPIS:
            raise ValueError("view kpi must be one of %s" % (VIEW_KPIS,))
        clean["kpi"] = state["kpi"]
    if "view" in state:
        clean["view"] = str(state["view"] or "")[:32]
    if "benchmark" in state:
        clean["benchmark"] = str(state["benchmark"] or "")[:32]
    if "benchmark_scope" in state:
        if state["benchmark_scope"] not in ("filters", "global"):
            raise ValueError("view benchmark_scope must be filters|global")
        clean["benchmark_scope"] = state["benchmark_scope"]
    if "rank_by" in state:
        if state["rank_by"] not in VIEW_RANKS:
            raise ValueError("view rank_by must be one of %s" % (VIEW_RANKS,))
        clean["rank_by"] = state["rank_by"]
    if "compare_mode" in state:
        if state["compare_mode"] not in ("campaigns", "creatives"):
            raise ValueError("view compare_mode must be campaigns|creatives")
        clean["compare_mode"] = state["compare_mode"]
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO saved_views (name, state_json, created_at, updated_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET"
        " state_json=excluded.state_json, updated_at=excluded.updated_at",
        (name, json.dumps(clean, sort_keys=True), now, now))
    conn.commit()
    row = conn.execute("SELECT id, state_json FROM saved_views WHERE name=?",
                       (name,)).fetchone()
    return {"id": row[0], "name": name, "state": json.loads(row[1])}


def list_views(conn):
    return [{"id": r[0], "name": r[1], "state": json.loads(r[2]),
             "updated_at": r[3]}
            for r in conn.execute(
                "SELECT id, name, state_json, updated_at FROM saved_views"
                " ORDER BY name").fetchall()]


def apply_action(conn, action, payload, prov, media_dir=None, actor="",
                 progress=None, cancelled=None):
    """progress(pct, stage)/cancelled() flow into the pipeline branch only;
    every other action ignores them (all existing callers unaffected)."""
    if action == "ingest":
        if not payload.get("platform"):
            raise ValueError("ingest needs a platform")
        if isinstance(payload.get("xlsx_b64"), str) and payload["xlsx_b64"]:
            import base64
            try:
                blob = base64.b64decode(payload["xlsx_b64"], validate=True)
            except Exception:
                raise ValueError("xlsx_b64 is not valid base64")
            rows, quarantined = ingest.parse_xlsx_report(
                blob, payload["platform"], payload.get("source", "upload"))
        elif isinstance(payload.get("csv"), str):
            rows, quarantined = ingest.parse_csv_report(
                payload["csv"], payload["platform"],
                payload.get("source", "upload"))
        else:
            raise ValueError("ingest needs csv text or xlsx_b64 plus platform")
        # Uploads dedup like every other import surface: re-uploading
        # the same file updates matching facts instead of doubling
        # totals. (Plain insert_rows() stays the append primitive.)
        counts = ingest.upsert_rows(conn, rows)
        return {"inserted": counts["inserted"], "updated": counts["updated"],
                "quarantined": quarantined,
                "quarantined_count": len(quarantined)}
    if action == "annotate":
        creative.save_annotation(conn, payload["creative_key"],
                                 payload["annotation"])
        return {"ok": True}
    if action == "verify":
        return {"ok": True,
                "annotation": creative.mark_verified(conn, payload["creative_key"])}
    if action == "pipeline":
        try:
            bundle = media.find_for_creative(
                conn, _media_dir(media_dir), payload["creative_key"])
        except ValueError:
            bundle = None
        from creative_intel import video as video_mod
        if bundle and (bundle.get("videos") and
                       not (bundle.get("audio") or bundle.get("images")) and
                       (getattr(prov, "mode", "mock") == "live" or
                        video_mod.have_ffmpeg())):
            # Upload MP4 -> Run Pipeline, end to end: decompose the
            # first stored video (ffmpeg, cached) into STT audio +
            # vision frames. Live mode always attempts this and fails
            # closed without ffmpeg; mock mode attempts it whenever
            # ffmpeg exists so the full extraction chain is provable
            # without provider keys, and skips it otherwise (mocks
            # need no media).
            if cancelled is not None and cancelled():
                from creative_intel.jobs import JobCancelled
                raise JobCancelled("job cancelled before video prepare")
            if progress is not None:
                progress(12, "video-prepare")
            prepared = video_mod.prepare(
                bundle["videos"][0],
                os.path.join(_media_dir(media_dir), "derived"))
            bundle = dict(bundle, audio=prepared["audio"],
                          images=prepared["images"],
                          image_times=prepared["image_times"],
                          duration_s=prepared["duration_s"])
            if progress is not None:
                progress(20, "video-prepare")
        terms = payload.get("brand_terms") or []
        if isinstance(terms, str):
            terms = [t.strip() for t in terms.split(",")]
        terms = [t for t in terms if isinstance(t, str) and t.strip()][:20]

        def _scaled(pct, _stage):
            if progress is not None:
                progress(20 + pct * 0.75, _stage)

        return creative.run_pipeline(conn, payload["creative_key"], prov,
                                     media=bundle, brand_terms=terms or None,
                                     progress=_scaled if progress else None,
                                     cancelled=cancelled)
    if action == "media-upload":
        if not isinstance(payload, dict) or not payload.get("creative_key"):
            raise ValueError("media upload needs creative_key")
        return media.save_media(
            conn, _media_dir(media_dir), payload["creative_key"],
            payload.get("filename", ""), payload.get("content_b64", ""),
            payload.get("mime"), uploaded_by=actor or "")
    if action == "connect-sheets":
        if not payload.get("platform"):
            raise ValueError("sheets import needs a platform")
        params = {"url": payload.get("url", ""),
                  "platform": payload["platform"]}
        bearer = payload.get("_google_bearer") or None
        out = sync.import_once(
            conn, "sheets",
            lambda: sync.fetch_job("sheets", params, bearer=bearer))
        sync.save_job(conn, "sheets", params, owner=actor)
        return out
    if action == "connect-drive":
        if not payload.get("platform"):
            raise ValueError("drive import needs a platform")
        params = {"url": payload.get("url", ""),
                  "platform": payload["platform"]}
        bearer = payload.get("_google_bearer") or None
        out = sync.import_once(
            conn, "drive",
            lambda: sync.fetch_job("drive", params, bearer=bearer))
        sync.save_job(conn, "drive", params, owner=actor)
        return out
    if action == "connect-meta":
        params = {"ad_account_id": payload.get("ad_account_id", ""),
                  "since": payload.get("since", ""),
                  "until": payload.get("until", "")}
        out = sync.import_once(
            conn, "meta", lambda: sync.fetch_job("meta", params))
        sync.save_job(conn, "meta", params, owner=actor)
        return out
    if action == "connect-tiktok":
        params = {"advertiser_id": payload.get("advertiser_id", ""),
                  "start_date": payload.get("start_date", ""),
                  "end_date": payload.get("end_date", "")}
        out = sync.import_once(
            conn, "tiktok", lambda: sync.fetch_job("tiktok", params))
        sync.save_job(conn, "tiktok", params, owner=actor)
        return out
    if action == "sync-now":
        source = payload.get("source", "")
        stored = sync.jobs(conn)
        if source not in stored:
            raise ValueError(
                "no saved sync job for %r: run a manual import first"
                % (source,))
        return sync.import_once(
            conn, source,
            lambda: sync.fetch_job(source, stored[source]))
    if action == "retention":
        # Manual uploads are stamped source='manual' so the quartile
        # synthesizer never overwrites them (it only rebuilds its own
        # 'quartile_synthesized' rows).
        conn.executemany(
            "INSERT OR REPLACE INTO retention (creative_key, t_sec,"
            " retention_pct, source)"
            " VALUES (?, ?, ?, 'manual')",
            [(payload["creative_key"], t, p) for t, p in payload["points"]])
        conn.commit()
        return {"ok": True}
    if action == "save-view":
        return save_view(conn, payload.get("name", ""),
                         payload.get("state", {}))
    if action == "delete-view":
        try:
            view_id = int(payload.get("id"))
        except (TypeError, ValueError):
            raise ValueError("delete-view needs an integer id")
        cur = conn.execute("DELETE FROM saved_views WHERE id=?", (view_id,))
        conn.commit()
        if not cur.rowcount:
            raise ValueError("no saved view #%d" % view_id)
        return {"ok": True, "deleted": view_id}
    raise ValueError("unknown action %r" % action)


def build_creatives_list(conn, q):
    """Creatives with cohort-correct scoped metrics (shared)."""
    cols = ["creative_key", "platform", "name", "duration_s",
            "status", "transcript"]
    rows = [dict(zip(cols, r)) for r in conn.execute(
        "SELECT creative_key, platform, name, duration_s, status,"
        " transcript FROM creatives")]
    from creative_intel import benchmarks as _bench
    scope = _bench.Scope.from_query(q).resolve(conn)
    norm = scope.normalized()
    ad_cols = [c[0] for c in conn.execute(
        "SELECT * FROM ads LIMIT 0").description]
    kept = []
    for r in rows:
        ad_rows = [dict(zip(ad_cols, v)) for v in conn.execute(
            "SELECT * FROM ads WHERE creative_key=?",
            (r["creative_key"],)).fetchall()]
        # Annotation axes (hook_type, creator_vs_branded) live on the
        # creative, not the ad rows: stamp them before cohort matching
        # so those filters constrain instead of hiding everything.
        ann_row = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (r["creative_key"],)).fetchone()
        if ann_row:
            import json as _json_ann
            try:
                _ann = _json_ann.loads(ann_row[0])
            except ValueError:
                _ann = {}
            for ad in ad_rows:
                ad.setdefault("hook_type", _ann.get("hook_type", "") or "")
                ad.setdefault("creator_vs_branded",
                              _ann.get("creator_vs_branded", "") or "")
        # Cohort-correct metrics: only rows passing the
        # shared scope feed the KPI aggregation (a Spain
        # filter must never show France-blended CPA; a
        # Campaign-A filter must never blend Campaign B).
        matched = [ad for ad in ad_rows
                   if _bench.match_filters(ad, norm)]
        if ad_rows and not matched:
            # Performance exists but nothing is inside
            # the scope: hide the card. A creative with
            # media but no performance rows yet stays
            # visible (zero metrics) so it can be
            # annotated and pipelined.
            continue
        agg_rows = matched
        spend = sum(v["spend"] for v in agg_rows)
        impr = sum(v["impressions"] for v in agg_rows)
        clicks = sum(v["clicks"] for v in agg_rows)
        conv = sum(v["conversions"] for v in agg_rows)
        views = sum(v["video_views"] for v in agg_rows)
        rev = sum(v["revenue"] for v in agg_rows)
        r["campaigns"] = sorted({v["campaign"] for v in agg_rows
                                 if v["campaign"]})
        # Most common format across the creative's rows ("" when none).
        _fmts = [v.get("format") or "" for v in agg_rows]
        r["format"] = max(set(_fmts), key=_fmts.count) if _fmts else ""
        # A14/A15: same pooled contract as benchmarks.kpis_for_rows
        # (currency metadata, mixed-scope money gating,
        # matched-population ROAS, registry vtr/view_rate split).
        _mscope = _bench.money_scope(agg_rows)
        _mixed = _mscope["mixed_currency"]
        _roas, _roas_cov = _bench.matched_roas(agg_rows)
        r["metrics"] = {
            "spend": round(spend, 2), "impressions": impr,
            "clicks": clicks, "conversions": conv,
            "video_views": views, "revenue": round(rev, 2),
            "currency": _mscope["currency"],
            "currencies": _mscope["currencies"],
            "mixed_currency": _mixed,
            "by_currency": _bench.by_currency(agg_rows),
            "cpm": (None if _mixed else (
                round(spend / impr * 1000, 2) if impr else None)),
            "vtr": _bench.pooled_registry_ratio(agg_rows, "vtr"),
            "view_rate": _bench.pooled_registry_ratio(
                agg_rows, "view_rate"),
            "ctr": round(clicks / impr, 4) if impr else None,
            "cpc": (None if _mixed else (
                round(spend / clicks, 2) if clicks else None)),
            "cpa": (None if _mixed else (
                round(spend / conv, 2) if conv else None)),
            "roas": None if _mixed else _roas,
            "roas_coverage": _roas_cov}
        r["scope"] = scope.describe()
        ann = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (r["creative_key"],)).fetchone()
        r["annotation"] = json.loads(ann[0]) if ann else None
        kept.append(r)
    return kept


COMPARE_RANK_METRICS = ("cpm", "vtr", "ctr", "cpc", "cpa", "roas")

COMPARE_RANK_DIRECTIONS = {"cpm": "lower", "vtr": "higher", "ctr": "higher",
                           "cpc": "lower", "cpa": "lower", "roas": "higher"}


def _attribute_table(anns):
    """Side-by-side creative attributes (None == not annotated).

    Mirrors the why-analysis inputs so the table and the narrative
    can never disagree about what was observed.
    """
    rows = []
    for label, get in (
            ("Hook type", lambda a: a.get("hook_type")),
            ("Hook modality", lambda a: a.get("hook_modality")),
            ("Creator vs branded", lambda a: a.get("creator_vs_branded")),
            ("Edit style", lambda a: a.get("edit_style")),
            ("Duration (s)", lambda a: a.get("duration_s")),
            ("Product first appears (s)",
             lambda a: _span_start(a, "product_seconds")),
            ("Brand first appears (s)",
             lambda a: _span_start(a, "brand_seconds")),
            ("Logo first appears (s)",
             lambda a: _span_start(a, "logo_seconds")),
            ("Audible brand mention (s)",
             lambda a: a.get("brand_audio_mention_s")),
            ("CTA", lambda a: (a.get("cta")
                               or (_slot_set(a, "cta") and "set") or None)),
            ("Supers", lambda a: a.get("supers") or None),
            ("Voiceover", lambda a: ("set" if _slot_set(a, "voiceover")
                                     else None)),
            ("Pace (cuts/min)", lambda a: a.get("pace_cuts_per_min")),
            ("Structure", lambda a: ", ".join(
                sorted(s for s in ((a.get("structure") or {}).keys())
                       if _slot_set(a, s))) or None),
            ("Verification status", lambda a: a.get("status"))):
        values = {}
        for key, ann in anns.items():
            try:
                values[key] = get(ann or {}) if ann else None
            except Exception:
                values[key] = None
        rows.append({"attribute": label, "values": values})
    return rows


def _rank_creatives(keys, per, rank_by):
    """Rank creative keys by rank_by (None always ranks last).

    Returns (ranking, winner); winner is None when every candidate's
    KPI is uncomputable. Never converts missing values to zero.
    """
    higher = COMPARE_RANK_DIRECTIONS[rank_by] == "higher"

    def _key(key):
        value = per.get(key, {}).get(rank_by)
        if value is None:
            return (1, 0.0)
        return (0, -value if higher else value)

    ranking = sorted(keys, key=_key)
    if all(per.get(key, {}).get(rank_by) is None for key in ranking):
        return ranking, None
    return ranking, ranking[0]


def build_compare(conn, q):
    """N-way creative compare with why-analysis (shared)."""
    from creative_intel import benchmarks as _bench2
    rank_by = (q.get("rank_by", ["cpa"])[0] or "cpa").lower()
    if rank_by not in COMPARE_RANK_METRICS:
        raise ValueError("rank_by must be one of %s"
                         % list(COMPARE_RANK_METRICS))
    legacy = [q.get("a", [""])[0], q.get("b", [""])[0]]
    keys = [k for k in q.get("key", []) if k]
    if not keys:
        keys = legacy
    seen, ordered = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    keys = ordered[:6]
    if len(ordered) > 6:
        raise ValueError("compare takes at most 6 creatives")
    if not keys:
        keys = ["", ""]
    scope = _bench2.Scope.from_query(q).resolve(conn)
    ad_cols = [c[0] for c in conn.execute(
        "SELECT * FROM ads LIMIT 0").description]
    out = {}
    for key in keys:
        rows = [dict(zip(ad_cols, v)) for v in conn.execute(
            "SELECT * FROM ads WHERE creative_key=?",
            (key,)).fetchall()]
        # Same scope as every other surface: a Spain
        # comparison never blends France rows.
        rows = [r for r in rows if scope.match(r)]
        spend = sum(r["spend"] for r in rows)
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        conv = sum(r["conversions"] for r in rows)
        ann = conn.execute("SELECT annotation_json FROM annotations"
                           " WHERE creative_key=?", (key,)).fetchone()
        # A14/A15: same pooled contract as benchmarks.kpis_for_rows
        # (currency metadata, mixed-scope money gating,
        # matched-population ROAS, registry vtr/view_rate split).
        _mscope = _bench2.money_scope(rows)
        _mixed = _mscope["mixed_currency"]
        _roas, _roas_cov = _bench2.matched_roas(rows)
        out[key] = {"spend": round(spend, 2),
                    "impressions": impr,
                    "clicks": clicks,
                    "conversions": conv,
                    "currency": _mscope["currency"],
                    "currencies": _mscope["currencies"],
                    "mixed_currency": _mixed,
                    "by_currency": _bench2.by_currency(rows),
                    "cpm": (None if _mixed else (
                        round(spend / impr * 1000, 2) if impr else None)),
                    "vtr": _bench2.pooled_registry_ratio(rows, "vtr"),
                    "view_rate": _bench2.pooled_registry_ratio(
                        rows, "view_rate"),
                    "ctr": round(clicks / impr, 4) if impr else None,
                    "cpc": (None if _mixed else (
                        round(spend / clicks, 2) if clicks else None)),
                    "cpa": (None if _mixed else (
                        round(spend / conv, 2) if conv else None)),
                    "roas": None if _mixed else _roas,
                    "roas_coverage": _roas_cov,
                    "scope": scope.describe(),
                    "annotation": json.loads(ann[0]) if ann else None}
    if len(keys) == 2:
        out["why"] = _creative_why(keys[0], keys[1],
                                   out.get(keys[0], {}),
                                   out.get(keys[1], {}))
    else:
        out["why"] = _multi_why(
            keys, {k: out.get(k, {}) for k in keys})
    ranking, winner = _rank_creatives(
        keys, {k: out.get(k, {}) for k in keys}, rank_by)
    out["keys"] = keys
    out["rank_by"] = rank_by
    out["ranking"] = ranking
    out["winner"] = winner
    # One winner, controlled by the selected rank_by: the pairwise and
    # N-way why-analyses crown a hardcoded CPA/CTR favourite, which
    # contradicts the ranking whenever another KPI is selected.
    if isinstance(out.get("why"), dict):
        out["why"]["top"] = winner
    out["attributes"] = _attribute_table(
        {k: (out.get(k, {}) or {}).get("annotation") for k in keys})
    out["scope"] = scope.describe()
    return out


def load_fixtures(db_path):
    conn = connect(db_path)
    prov = providers.Providers(db_path=db_path)
    total = 0
    for fname, platform in (("Meta Sample.csv", "meta"),
                            ("TikTok Sample.csv", "tiktok")):
        path = os.path.join(FIXTURES, fname)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            payload = {"platform": platform, "source": "fixture",
                       "csv": f.read()}
        total += apply_action(conn, "ingest", payload, prov)["inserted"]
        replay.log(conn, "ingest", payload)
    rpath = os.path.join(FIXTURES, "Retention Sample.csv")
    if os.path.exists(rpath):
        import csv as _csv
        with open(rpath) as f:
            by_key = {}
            for row in _csv.DictReader(f):
                by_key.setdefault(row["creative_key"], []).append(
                    (float(row["t_sec"]), float(row["retention_pct"])))
        for key, points in by_key.items():
            payload = {"creative_key": key, "points": points}
            apply_action(conn, "retention", payload, prov)
            replay.log(conn, "retention", payload)
    for (key,) in conn.execute("SELECT creative_key FROM creatives").fetchall():
        payload = {"creative_key": key}
        apply_action(conn, "pipeline", payload, prov)
        replay.log(conn, "pipeline", payload)
    conn.close()
    return total


# ---------------------------------------------------------------------------
# Synthetic demo dataset (clearly marked source="demo", never real data).
# ---------------------------------------------------------------------------

_DEMO_CAMPAIGNS = (
    # name, client, team, platforms+share, vertical, market, weight, objective
    ("Spring Skincare Launch", "GlowNaturally", "Growth",
     (("meta", 0.55), ("tiktok", 0.45)), "Beauty", "UK", 0.16, "Conversions"),
    ("Built For Real Life", "Everyday Essentials", "Growth",
     (("meta", 0.6), ("tiktok", 0.4)), "Consumer Goods", "Australia", 0.13, "Conversions"),
    ("Everyday Energy", "VitaWell", "Growth",
     (("tiktok", 1.0),), "Wellness", "US", 0.12, "Traffic"),
    ("Adventure Awaits", "TrailNorth", "Brand",
     (("meta", 0.5), ("tiktok", 0.5)), "Travel", "Canada", 0.11, "Conversions"),
    ("Your Routine Simplified", "WellnessCo", "Brand",
     (("meta", 1.0),), "Wellness", "UK", 0.10, "Leads"),
    ("Better Coffee Mornings", "Morning Brew Co", "Brand",
     (("tiktok", 0.6), ("meta", 0.4)), "Food & Beverage", "Australia", 0.10, "Conversions"),
    ("Move More", "Motion", "Performance",
     (("tiktok", 0.55), ("meta", 0.45)), "Fitness", "US", 0.09, "Traffic"),
    ("Smarter Home Living", "Nook", "Performance",
     (("meta", 0.6), ("tiktok", 0.4)), "Technology", "Germany", 0.08, "Conversions"),
    ("Everyday Style", "Thread", "Performance",
     (("meta", 0.5), ("tiktok", 0.5)), "Fashion", "France", 0.06, "Conversions"),
    ("Discover Something New", "Wander", "Performance",
     (("tiktok", 0.6), ("meta", 0.4)), "Travel", "Singapore", 0.05, "Traffic"),
)

_DEMO_CREATIVES = (
    # key, display name, campaign, platform, format, secs, hook, modality,
    # style, creator mode, brand_first_s, product_first_s
    ("demo-glowskin-01", "Glowing Skin Made Easy", "Spring Skincare Launch",
     "tiktok", "9:16 Video", 18, "question", "spoken", "ugc", "creator", 3.0, 2.0),
    ("demo-reallife-01", "Built For Real Life", "Built For Real Life",
     "meta", "4:5 Video", 25, "story", "spoken", "testimonial", "creator", 5.0, 8.0),
    ("demo-energy-01", "Morning Routine", "Everyday Energy",
     "tiktok", "9:16 Video", 15, "demo_open", "visual", "product_demo", "creator", 4.0, 1.5),
    ("demo-trail-01", "Problem / Solution", "Adventure Awaits",
     "meta", "16:9 Video", 30, "pattern_interrupt", "visual", "cinematic", "branded", 2.0, 6.0),
    ("demo-routine-01", "Creator Testimonial", "Your Routine Simplified",
     "meta", "1:1 Video", 22, "social_proof", "spoken", "talking_head", "creator", 6.0, 4.0),
    ("demo-coffee-01", "Quick Product Demo", "Better Coffee Mornings",
     "tiktok", "9:16 Video", 12, "demo_open", "text", "product_demo", "hybrid", 3.5, 1.0),
    ("demo-move-01", "Three Reasons Why", "Move More",
     "tiktok", "9:16 Video", 20, "bold_claim", "spoken", "montage", "creator", 5.0, 3.0),
    ("demo-nook-01", "Before & After", "Smarter Home Living",
     "meta", "16:9 Video", 28, "pattern_interrupt", "visual", "product_demo", "branded", 4.0, 7.0),
    ("demo-thread-01", "Everyday Use Case", "Everyday Style",
     "meta", "4:5 Video", 16, "story", "visual", "ugc", "hybrid", 5.5, 2.5),
    ("demo-wander-01", "Limited-Time Offer", "Discover Something New",
     "tiktok", "9:16 Video", 14, "offer", "text", "montage", "creator", 2.5, 2.0),
)

_DEMO_DAYS = 120
# Approximate reference-scale totals across the full window.
_DEMO_TOTALS = {"impressions": 125_400_000, "clicks": 1_800_000,
                "spend": 412_600.0, "revenue": 1_485_000.0}
# Linear growth slopes (fraction of start volume per full window) tuned
# so second-half vs first-half comparisons read roughly: impressions
# +24%, clicks +32%, spend +12%, revenue +43% (ROAS about +28%).
_DEMO_RAMPS = {"impressions": 0.545, "clicks": 0.73, "spend": 0.27,
               "revenue": 0.98}
# The ramp lifts the window mean by (1 + slope / 2); divide it back out
# so the totals above are what the backend actually aggregates.
_DEMO_MEAN = {m: 1.0 + s / 2.0 for m, s in _DEMO_RAMPS.items()}


def _demo_annotation(spec):
    """Valid v0 annotation for a demo creative (human_verified demo labels)."""
    (key, _name, _camp, _plat, _fmt, secs, hook, modality, style,
     mode, brand_s, product_s) = spec
    ann = creative.blank_annotation()
    ann.update({"hook_type": hook, "hook_modality": modality,
                "hook_confidence": 0.9, "creator_vs_branded": mode,
                "creator_confidence": 0.9, "edit_style": style,
                "edit_confidence": 0.85, "duration_s": float(secs),
                "pace_cuts_per_min": 8.0, "status": "human_verified",
                "brand_seconds": [{"start_s": brand_s,
                                   "end_s": round(brand_s + 2.0, 1)}],
                "product_seconds": [{"start_s": product_s,
                                     "end_s": round(product_s + 3.0, 1)}],
                "logo_seconds": [{"start_s": round(brand_s + 0.5, 1),
                                  "end_s": round(brand_s + 1.5, 1)}]})
    hook_end = min(3.0, secs)
    ann["structure"] = {
        slot: {"start_s": 0.0, "end_s": hook_end if slot == "hook" else float(secs),
               "confidence": 0.9}
        for slot in creative.STRUCTURE_SLOTS}
    return ann


def _demo_retention_points(secs):
    """Plausible decaying retention curve for a demo creative."""
    import math as _math
    steps = 8
    return [(round(secs * i / (steps - 1), 1),
             round(100.0 * _math.exp(-2.2 * i / (steps - 1)), 1))
            for i in range(steps)]


#: Showcase owner for seeded analyst rows. Analyst conversations are
#: strictly per-employee (a cross-owner read is a 404 by design, and
#: that isolation must never weaken for the demo), so seeded chats
#: carry this fixed showcase string instead of impersonating a real
#: employee. No employees/auth rows are created for it — it is pure
#: attribution, like source="demo" on the ads rows.
DEMO_ANALYST_OWNER = "demo"

#: Saved views seeded alongside the demo dataset: four benchmark
#: cards (view="benchmark", the first GET /api/views rows the
#: Benchmarks page renders) plus three compare views (view="compare",
#: entries the Saved Insights grid opens on /compare). Filter values
#: name real demo rows so applying a card analyses the seeded
#: dataset, never an empty scope.
_DEMO_SAVED_VIEWS = (
    ("Demo \u2014 Benchmark: Platform",
     {"filters": {}, "kpi": "roas", "view": "benchmark",
      "benchmark": "platform", "benchmark_scope": "filters",
      "rank_by": "roas"}),
    ("Demo \u2014 Benchmark: Hook Type",
     {"filters": {"platform": ["tiktok"]}, "kpi": "ctr",
      "view": "benchmark", "benchmark": "hook_type",
      "benchmark_scope": "filters", "rank_by": "ctr"}),
    ("Demo \u2014 Benchmark: Creator Vs Branded",
     {"filters": {"vertical": ["Beauty"]}, "kpi": "cpa",
      "view": "benchmark", "benchmark": "creator_vs_branded",
      "benchmark_scope": "global", "rank_by": "cpa"}),
    ("Demo \u2014 Benchmark: Format",
     {"filters": {"market": ["UK"]}, "kpi": "cpm", "view": "benchmark",
      "benchmark": "format", "benchmark_scope": "filters",
      "rank_by": "cpm"}),
    ("Demo \u2014 Compare: Campaigns (ROAS)",
     {"filters": {"campaign": ["Spring Skincare Launch",
                               "Built For Real Life"]},
      "kpi": "roas", "view": "compare", "benchmark": "campaign",
      "benchmark_scope": "filters", "rank_by": "roas"}),
    ("Demo \u2014 Compare: Creatives (CTR)",
     {"filters": {"platform": ["tiktok"]}, "kpi": "ctr",
      "view": "compare", "benchmark": "hook_type",
      "benchmark_scope": "filters", "rank_by": "ctr"}),
    ("Demo \u2014 Compare: Markets (CPA)",
     {"filters": {"market": ["UK", "US"]}, "kpi": "cpa",
      "view": "compare", "benchmark": "platform",
      "benchmark_scope": "global", "rank_by": "cpa"}),
)

#: Analyst showcase turns (question, scope, objective, language): two
#: full-analysis turns so stored findings persist, plus one
#: recommendations turn for recent-chat variety. Every message and
#: finding is computed from the seeded rows by answer_turn — never
#: invented copy.
_DEMO_ANALYST_TURNS = (
    ("Which hook types drive the highest CTR?", {}, "reach", "en"),
    ("Compare hook performance across creatives.", {}, "reach", "en"),
    ("What are your recommendations for the next campaign?",
     {}, "conversions", "en"),
)


def _seed_demo_views(conn):
    """Insert missing demo saved views (per-name skip, never overwrite).

    A re-seed is a no-op and demo edits made during the session
    survive: only names absent from saved_views are written, through
    the same save_view() validation the API uses. Returns how many
    views were inserted.
    """
    inserted = 0
    for name, state in _DEMO_SAVED_VIEWS:
        present = conn.execute(
            "SELECT 1 FROM saved_views WHERE name=?", (name,)).fetchone()
        if present:
            continue
        save_view(conn, name, dict(state))
        inserted += 1
    return inserted


def _seed_demo_analyst(conn):
    """Run the demo analyst showcase turns (skip when already present).

    Real deterministic turns under DEMO_ANALYST_OWNER: one user plus
    one assistant message per conversation, findings persisted with
    scope + dataset version exactly as a live turn stores them.
    Returns how many conversations were created.
    """
    from creative_intel import analyst_chat

    def _seed_owner(owner):
        here = conn.execute(
            "SELECT 1 FROM analyst_conversations WHERE owner_employee_id=?"
            " LIMIT 1", (owner,)).fetchone()
        if here:
            return 0
        made = 0
        for question, scope, objective, language in _DEMO_ANALYST_TURNS:
            analyst_chat.answer_turn(conn, owner, question, None,
                                     scope=dict(scope), objective=objective,
                                     language=language)
            made += 1
        return made

    created = _seed_owner(DEMO_ANALYST_OWNER)
    # Conversations are private per employee, so a demo-owner set alone
    # never shows up in anyone's Recent Chats: mirror the same showcase
    # turns to every employee present (per-owner skip, never overwrite).
    # On a fresh boot there are no employees yet; the admin reseed path
    # backfills them idempotently.
    try:
        owners = [r[0] for r in conn.execute("SELECT id FROM employees")]
    except Exception:
        owners = []
    for owner in owners:
        if owner != DEMO_ANALYST_OWNER:
            created += _seed_owner(owner)
    return created


def load_demo_dataset(db_path, media_dir=None):
    """Seed the synthetic demo dataset (source="demo").

    Ten campaigns and ten annotated creatives with ~120 days of daily
    rows ending yesterday, so charts, benchmarks, comparisons and
    KpiTrend all compute from real seeded rows. Ingest upserts, so a
    repeated load inserts nothing new; annotations upsert by key.
    Each demo creative also gains a distinct seeded image asset (an
    uploaded-media row, skipped when one already exists), so the
    thumbnail endpoint serves real per-creative art instead of the
    generated fallback. Showcase content for populated screens rides
    along: seven demo saved views (four benchmark cards, three
    compare views) plus three demo-owner analyst conversations with
    stored findings, every row demo-attributed and skipped when
    already present. media_dir overrides the media store (tests
    pass an isolated directory); the default is the app media store.
    Returns the number of ads rows inserted on this call.
    """
    import csv as _csv
    import datetime as _dt
    import io as _io
    import random as _random

    conn = connect(db_path)
    prov = providers.Providers(db_path=db_path)
    rng = _random.Random(20260911)
    end = _dt.date.today() - _dt.timedelta(days=1)
    days = [_dt.date.toordinal(end) - (_DEMO_DAYS - 1 - i)
            for i in range(_DEMO_DAYS)]
    day_iso = [_dt.date.fromordinal(o).isoformat() for o in days]

    header = ["Campaign", "Ad Name", "Creative Key", "Client", "Team", "Project",
              "Vertical", "Market", "Objective", "Funnel Stage", "Date",
              "Spend", "Impressions", "Clicks", "Conversions",
              "Video Views", "Revenue", "Creative Format", "Campaign Id"]
    total = 0
    for platform in ("meta", "tiktok"):
        buf = _io.StringIO()
        writer = _csv.writer(buf)
        writer.writerow(header)
        for day_i, iso in enumerate(day_iso):
            t = day_i / (_DEMO_DAYS - 1)
            for ci, camp in enumerate(_DEMO_CAMPAIGNS):
                (name, client, team, plats, vertical, market, weight,
                 objective) = camp
                share = dict(plats).get(platform)
                if not share:
                    continue
                impr = (_DEMO_TOTALS["impressions"] * weight * share
                        / _DEMO_DAYS / _DEMO_MEAN["impressions"]
                        * (1.0 + _DEMO_RAMPS["impressions"] * t))
                impr *= 1.0 + rng.uniform(-0.15, 0.15)
                clicks = (_DEMO_TOTALS["clicks"] * weight * share
                          / _DEMO_DAYS / _DEMO_MEAN["clicks"]
                          * (1.0 + _DEMO_RAMPS["clicks"] * t))
                clicks *= 1.0 + rng.uniform(-0.15, 0.15)
                spend = (_DEMO_TOTALS["spend"] * weight * share
                         / _DEMO_DAYS / _DEMO_MEAN["spend"]
                         * (1.0 + _DEMO_RAMPS["spend"] * t))
                spend *= 1.0 + rng.uniform(-0.12, 0.12)
                revenue = (_DEMO_TOTALS["revenue"] * weight * share
                           / _DEMO_DAYS / _DEMO_MEAN["revenue"]
                           * (1.0 + _DEMO_RAMPS["revenue"] * t))
                revenue *= 1.0 + rng.uniform(-0.15, 0.15)
                conv = clicks * 0.02 * (1.0 + rng.uniform(-0.1, 0.1))
                views = impr * 0.35 * (1.0 + rng.uniform(-0.1, 0.1))
                spec = _DEMO_CREATIVES[ci]
                writer.writerow([
                    name, spec[1], spec[0], client, team, client + " FY26",
                    vertical, market, objective, "Lower", iso,
                    round(spend, 2), int(impr), int(clicks), round(conv, 1),
                    int(views), round(revenue, 2), spec[4],
                    "DEMO-%02d" % (ci + 1)])
        payload = {"platform": platform, "source": "demo",
                   "csv": buf.getvalue()}
        total += apply_action(conn, "ingest", payload, prov)["inserted"]
    for spec in _DEMO_CREATIVES:
        creative.save_annotation(conn, spec[0], _demo_annotation(spec))
        apply_action(conn, "retention",
                     {"creative_key": spec[0],
                      "points": _demo_retention_points(spec[5])}, prov)
    store = _media_dir(media_dir)
    media.ensure_schema(conn)
    for spec in _DEMO_CREATIVES:
        key = spec[0]
        has_image = conn.execute(
            "SELECT 1 FROM media WHERE creative_key=?"
            " AND mime LIKE 'image/%' LIMIT 1", (key,)).fetchone()
        if not has_image:
            media.save_media_bytes(conn, store, key, key + ".png",
                                   demo_art.art_for_key(key))
    # Showcase content for populated screens: saved benchmark cards +
    # compare views (global, every viewer) and demo-owner analyst
    # chats with stored findings (owner-scoped like all analyst
    # history). Each step skips what is present, so reloads insert
    # nothing new; the returned count stays ads-only, exactly as
    # before, and no accounts/uploads/auth rows are touched.
    _seed_demo_views(conn)
    _seed_demo_analyst(conn)
    conn.commit()
    conn.close()
    return total


def _csv_param(value):
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(str(item).split(","))
        return [v.strip() for v in out if v.strip()]
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def expert2_compare_route(conn, query):
    from creative_intel import benchmarks as _bench
    campaigns = _csv_param(query.get("campaigns", [""])[0]
                           if "campaigns" in query else query.get("campaign", [""]))
    rank_by = (query.get("rank_by", ["cpa"])[0] or "cpa").lower()
    # ?campaign(s)= names the candidates; every other axis scopes them.
    scope = _bench.Scope.from_query(
        query, ignore=("campaign", "campaigns", "rank_by", "metric",
                       "id", "name"))
    return _bench.compare_campaigns(
        conn, campaigns or None, rank_by=rank_by, filters=scope)


def expert2_cohort_build_route(conn, query):
    from creative_intel import cohorts as _cohorts
    metric = (query.get("metric", ["cpa"])[0] or "cpa").lower()
    if query.get("id", [""])[0]:
        try:
            cohort_id = int(query["id"][0])
        except (TypeError, ValueError):
            raise ValueError("cohort id must be an integer")
        return _cohorts.build_cohort(conn, cohort_id=cohort_id, metric=metric)
    if query.get("name", [""])[0]:
        return _cohorts.build_cohort(conn, name=query["name"][0], metric=metric)
    # The whole active scope is copied: every filter-bar axis the
    # benchmarks understand, including campaign, exact date and the
    # date range. Include/exclude project lists override afterwards.
    filt = {}
    for key in ("vertical", "platform", "funnel", "objective", "market",
                "client", "campaign", "date", "date_from", "date_to"):
        vals = _csv_param(query.get(key, [""])[0]) if key in query else []
        if vals:
            filt[key] = vals
    for key in ("include_projects", "exclude_projects"):
        vals = _csv_param(query.get(key, [""])[0]) if key in query else []
        if vals:
            filt[key] = vals
    return _cohorts.build_cohort(conn, filters=filt, metric=metric)


def expert2_report_route(conn, payload):
    from creative_intel import benchmarks as _bench
    # Same review-to-zero gate as /api/export: annotation-derived
    # insights must not ship in official reports while QA reviews
    # are pending. override=True is honoured and logged, like export.
    override = bool(payload.get("override"))
    if not override:
        try:
            export_gate.check_reviews(conn)
        except export_gate.ExportBlocked as e:
            raise ValueError(str(e))
    campaigns = payload.get("campaigns") or None
    kpis = payload.get("kpis") or ["cpa", "ctr"]
    benchmark_sel = payload.get("benchmark")
    fmt = payload.get("format", "one-pager")
    result = _bench.build_report(conn, campaigns, kpis, benchmark_sel, fmt,
                                 strict_human=bool(payload.get("strict_human")),
                                 filters=payload.get("filters"),
                                 benchmark_scope=payload.get(
                                     "benchmark_scope", "filters"),
                                 rank_by=payload.get("rank_by"))
    if override:
        replay.log(conn, "report-override",
                   {"campaigns": campaigns, "format": fmt,
                    "kpis": kpis, "override": True})
    return result

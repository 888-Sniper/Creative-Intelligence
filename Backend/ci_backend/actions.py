"""Shared product logic: analytics actions used by every server shell.

Moved verbatim from the legacy stdlib server so the FastAPI app and
any remaining callers run identical logic. No HTTP or auth here.
"""

from __future__ import annotations

import json
import os
import sqlite3

from creative_intel import (benchmarks, creative, export_gate,
                            ingest, media, providers, qa, replay, retention,
                            schema, sync)

BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", ".."))
WEB_INDEX = os.path.normpath(os.path.join(BASE, "Web", "Index.html"))
ASSETS_DIR = os.path.normpath(os.path.join(BASE, "Web", "assets"))


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
             "rank_by")


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
        unknown_axes = sorted(set(state["filters"]) - set(_bench.Scope.AXES))
        if unknown_axes:
            raise ValueError("unknown view filter axes: %s" % unknown_axes)
        _bench.Scope(state["filters"]).normalized()  # validates values
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


def apply_action(conn, action, payload, prov, media_dir=None, actor=""):
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
            prepared = video_mod.prepare(
                bundle["videos"][0],
                os.path.join(_media_dir(media_dir), "derived"))
            bundle = dict(bundle, audio=prepared["audio"],
                          images=prepared["images"],
                          image_times=prepared["image_times"],
                          duration_s=prepared["duration_s"])
        terms = payload.get("brand_terms") or []
        if isinstance(terms, str):
            terms = [t.strip() for t in terms.split(",")]
        terms = [t for t in terms if isinstance(t, str) and t.strip()][:20]
        return creative.run_pipeline(conn, payload["creative_key"], prov,
                                     media=bundle, brand_terms=terms or None)
    if action == "media-upload":
        return media.save_media(
            conn, _media_dir(media_dir), payload["creative_key"],
            payload.get("filename", ""), payload.get("content_b64", ""),
            payload.get("mime"))
    if action == "connect-sheets":
        if not payload.get("platform"):
            raise ValueError("sheets import needs a platform")
        params = {"url": payload.get("url", ""),
                  "platform": payload["platform"]}
        out = sync.import_once(
            conn, "sheets", lambda: sync.fetch_job("sheets", params))
        sync.save_job(conn, "sheets", params, owner=actor)
        return out
    if action == "connect-drive":
        if not payload.get("platform"):
            raise ValueError("drive import needs a platform")
        params = {"url": payload.get("url", ""),
                  "platform": payload["platform"]}
        out = sync.import_once(
            conn, "drive", lambda: sync.fetch_job("drive", params))
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
    scope = _bench.Scope.from_query(q)
    norm = scope.normalized()
    ad_cols = [c[0] for c in conn.execute(
        "SELECT * FROM ads LIMIT 0").description]
    kept = []
    for r in rows:
        ad_rows = [dict(zip(ad_cols, v)) for v in conn.execute(
            "SELECT * FROM ads WHERE creative_key=?",
            (r["creative_key"],)).fetchall()]
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
        r["metrics"] = {
            "spend": round(spend, 2), "impressions": impr,
            "clicks": clicks, "conversions": conv,
            "video_views": views, "revenue": round(rev, 2),
            "cpm": round(spend / impr * 1000, 2) if impr else None,
            "vtr": round(views / impr, 4) if impr else None,
            "ctr": round(clicks / impr, 4) if impr else None,
            "cpc": round(spend / clicks, 2) if clicks else None,
            "cpa": round(spend / conv, 2) if conv else None,
            "roas": round(rev / spend, 4) if spend else None}
        r["scope"] = scope.describe()
        ann = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (r["creative_key"],)).fetchone()
        r["annotation"] = json.loads(ann[0]) if ann else None
        kept.append(r)
    return kept


def build_compare(conn, q):
    """N-way creative compare with why-analysis (shared)."""
    from creative_intel import benchmarks as _bench2
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
    scope = _bench2.Scope.from_query(q)
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
        views = sum(r["video_views"] or 0 for r in rows)
        revenue = sum(r["revenue"] or 0 for r in rows)
        ann = conn.execute("SELECT annotation_json FROM annotations"
                           " WHERE creative_key=?", (key,)).fetchone()
        out[key] = {"spend": round(spend, 2),
                    "impressions": impr,
                    "clicks": clicks,
                    "conversions": conv,
                    "cpm": round(spend / impr * 1000, 2) if impr else None,
                    "vtr": round(views / impr, 4) if impr else None,
                    "ctr": round(clicks / impr, 4) if impr else None,
                    "cpc": round(spend / clicks, 2) if clicks else None,
                    "cpa": round(spend / conv, 2) if conv else None,
                    "roas": round(revenue / spend, 4) if spend else None,
                    "scope": scope.describe(),
                    "annotation": json.loads(ann[0]) if ann else None}
    if len(keys) == 2:
        out["why"] = _creative_why(keys[0], keys[1],
                                   out.get(keys[0], {}),
                                   out.get(keys[1], {}))
    else:
        out["why"] = _multi_why(
            keys, {k: out.get(k, {}) for k in keys})
    out["keys"] = keys
    out["scope"] = scope.describe()
    return out


def load_fixtures(db_path):
    conn = connect(db_path)
    prov = providers.Providers()
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
    filt = {}
    for key in ("vertical", "platform", "funnel", "objective", "market", "client"):
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

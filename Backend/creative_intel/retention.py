"""Retention drop-off joined to annotation timestamps.

join_segments maps each annotated structure slot to the retention
lost inside it. drop_events turns those into seekable moments
(video timeline -> retention curve -> drop event -> creative
element), and patterns aggregates drop events across every
scoped creative so the app can answer "where do Beauty creatives
normally lose viewers?".
"""

DROP_PTS_MIN = 5.0


def _structure(conn, creative_key):
    import json
    row = conn.execute("SELECT annotation_json FROM annotations WHERE creative_key=?",
                       (creative_key,)).fetchone()
    if not row:
        raise ValueError("no annotation for %r" % creative_key)
    return json.loads(row[0])


SYNTH_SOURCE = "quartile_synthesized"


def synthesize_from_quartiles(conn):
    """Build retention curves from imported view quartiles.

    Meta/TikTok exports carry views_25/50/75/100 per ad row but no
    time series. For every creative, quartile views are summed across
    its ads rows and converted to % of impressions at 0/25/50/75/100%
    of duration (t=0 is 100% by definition: everyone who counted as
    an impression saw the first frame). Duration comes from
    creatives.duration_s, else the annotation, else 30s.
    Manual rows always win: a creative with any source='manual' row
    gets no synthetic points and keeps every manual point, so partial
    hand-supplied curves are never collapsed by a sync. Rows
    previously synthesized (source = 'quartile_synthesized') are
    deleted and rebuilt, so re-imports with changed quartile metrics
    refresh the curve instead of going stale. Returns the number of
    creatives (re)built.
    """
    import json
    manual = {r[0] for r in conn.execute(
        "SELECT DISTINCT creative_key FROM retention"
        " WHERE source='manual'").fetchall()}
    cols = [c[0] for c in conn.execute(
        "SELECT * FROM ads LIMIT 0").description]
    by_key = {}
    for v in conn.execute("SELECT * FROM ads").fetchall():
        row = dict(zip(cols, v))
        key = row.get("creative_key")
        if not key or key in manual:
            continue
        try:
            missing = set(json.loads(row.get("missing_json") or "[]"))
        except ValueError:
            missing = set()
        agg = by_key.setdefault(
            key, {"impr": 0, "q": [0, 0, 0, 0], "seen": [0, 0, 0, 0]})
        agg["impr"] += row.get("impressions") or 0
        for i, col in enumerate(("views_25", "views_50", "views_75",
                                 "views_100")):
            # A blank quartile cell is missing, never a measured zero:
            # only rows that actually report the quartile feed its sum.
            if col not in missing:
                agg["q"][i] += row.get(col) or 0
                agg["seen"][i] += 1
    done = 0
    for key, agg in sorted(by_key.items()):
        # Stale synthetic points go even when there is nothing to
        # rebuild from: otherwise a re-import that drops all quartile
        # data leaves a dead curve behind.
        conn.execute("DELETE FROM retention WHERE creative_key=?"
                     " AND source=?", (key, SYNTH_SOURCE))
        if agg["impr"] <= 0 or not any(agg["seen"]):
            continue
        dur = conn.execute("SELECT duration_s FROM creatives WHERE creative_key=?",
                           (key,)).fetchone()
        duration = (dur[0] if dur and dur[0] else 0) or 0
        if not duration:
            ann = conn.execute("SELECT annotation_json FROM annotations"
                               " WHERE creative_key=?", (key,)).fetchone()
            if ann:
                try:
                    duration = json.loads(ann[0]).get("duration_s") or 0
                except ValueError:
                    duration = 0
        duration = float(duration) if duration else 30.0
        pts = [(0.0, 100.0)]
        for frac, views, n in zip((0.25, 0.5, 0.75, 1.0), agg["q"],
                                  agg["seen"]):
            # Quartiles no row reported contribute no point: a 0%
            # crash-and-recovery mid-curve is a data gap, not a drop.
            if not n:
                continue
            pts.append((round(frac * duration, 2),
                        round(min(100.0, views * 100.0 / agg["impr"]), 2)))
        conn.executemany(
            "INSERT INTO retention (creative_key, t_sec, retention_pct,"
            " source) VALUES (?, ?, ?, ?)",
            [(key, t, p, SYNTH_SOURCE) for t, p in pts])
        done += 1
    return done


def _curve(conn, creative_key):
    curve = conn.execute(
        "SELECT t_sec, retention_pct FROM retention WHERE creative_key=?"
        " ORDER BY t_sec", (creative_key,)).fetchall()
    if not curve:
        raise ValueError("no retention curve for %r" % creative_key)
    return [(float(t), float(p)) for t, p in curve]


def join_segments(conn, creative_key):
    """Per-structure-segment retention drop: first vs last curve point inside."""
    structure = _structure(conn, creative_key).get("structure", {})
    curve = _curve(conn, creative_key)
    out = []
    for slot, seg in structure.items():
        try:
            start, end = float(seg["start_s"]), float(seg["end_s"])
        except (KeyError, TypeError, ValueError):
            continue
        pts = [(t, p) for t, p in curve if start <= t <= end]
        if not pts:
            out.append({"segment": slot, "drop_pts": 0.0, "n_points": 0,
                        "start_s": start, "end_s": end,
                        "from_pct": None, "to_pct": None})
        else:
            out.append({"segment": slot,
                        "drop_pts": round(pts[0][1] - pts[-1][1], 2),
                        "n_points": len(pts),
                        "start_s": start, "end_s": end,
                        "from_pct": round(pts[0][1], 2),
                        "to_pct": round(pts[-1][1], 2)})
    return out


def _span_min(spans):
    starts = [s.get("start_s") for s in spans or []
              if isinstance(s, dict)
              and isinstance(s.get("start_s"), (int, float))
              and not isinstance(s.get("start_s"), bool)]
    return min(starts) if starts else None


def curve(conn, creative_key):
    """Full retention curve plus timeline markers for the graph.

    Returns every stored (t, pct) point plus the creative moments
    worth drawing as vertical markers: hook window, first product /
    brand / logo visibility, CTA start, and duration. The UI draws
    retention-%-vs-time from this; drop_events() supplies the
    clickable drop windows overlaid on top.
    """
    ann = _structure(conn, creative_key)
    pts = _curve(conn, creative_key)
    structure = ann.get("structure") or {}

    def _slot(name):
        seg = structure.get(name) or {}
        try:
            s0, s1 = float(seg.get("start_s", 0)), float(seg.get("end_s", 0))
        except (TypeError, ValueError):
            return None
        return {"start_s": s0, "end_s": s1} if s1 > s0 else None

    hook = _slot("hook")
    cta = _slot("cta")
    return {"creative_key": creative_key,
            "points": [{"t": t, "p": p} for t, p in pts],
            "markers": {
                "hook": hook,
                "product_s": _span_min(ann.get("product_seconds")),
                "brand_s": _span_min(ann.get("brand_seconds")),
                "logo_s": _span_min(ann.get("logo_seconds")),
                "cta_s": (cta or {}).get("start_s"),
                "duration_s": ann.get("duration_s")},
            "hook_modality": (ann.get("hook_modality") or "unknown")}


def _span_covers(spans, t):
    for s in spans or []:
        if not isinstance(s, dict):
            continue
        try:
            if float(s.get("start_s", 0)) <= t <= float(s.get("end_s", 0)):
                return True
        except (TypeError, ValueError):
            continue
    return False


def element_at(annotation, t):
    """What creative element was occurring at second t.

    Returns the structure slot containing t plus which timed
    elements (product demo, brand/logo visible, CTA set, voiceover
    running) overlapped that moment. Pure annotation read: no
    causal claim, just co-occurrence for the drop-event view.
    """
    ann = annotation or {}
    structure = ann.get("structure") or {}
    slot, start, end = None, None, None
    for name, seg in structure.items():
        if not isinstance(seg, dict):
            continue
        try:
            s0, s1 = float(seg.get("start_s", 0)), float(seg.get("end_s", 0))
        except (TypeError, ValueError):
            continue
        if s1 > s0 and s0 <= t <= s1:
            slot, start, end = name, s0, s1
            break
    cta = ((ann.get("structure") or {}).get("cta") or {})
    cta_set = bool(isinstance(cta, dict)
                   and (cta.get("end_s") or 0) > (cta.get("start_s") or 0))
    vo = ((ann.get("structure") or {}).get("voiceover") or {})
    voiceover = bool(isinstance(vo, dict)
                     and (vo.get("end_s") or 0) > (vo.get("start_s") or 0))
    return {"slot": slot, "slot_start_s": start, "slot_end_s": end,
            "hook_type": ann.get("hook_type"),
            "hook_modality": ann.get("hook_modality") or "unknown",
            "creator_vs_branded": ann.get("creator_vs_branded"),
            "product_demo": _span_covers(ann.get("product_seconds"), t),
            "brand_visible": _span_covers(ann.get("brand_seconds"), t),
            "logo_visible": _span_covers(ann.get("logo_seconds"), t),
            "cta_present": cta_set or bool(ann.get("cta")),
            "voiceover": voiceover}


def drop_events(conn, creative_key, min_drop_pts=DROP_PTS_MIN):
    """Seekable drop moments for one creative, steepest first.

    Each event carries the curve window (from/to seconds and pct),
    the drop in percentage points, and the creative element under
    it via element_at. Events below min_drop_pts are noise, not
    moments, and are left out.
    """
    ann = _structure(conn, creative_key)
    events = []
    for seg in join_segments(conn, creative_key):
        if seg["n_points"] < 2 or seg["drop_pts"] < min_drop_pts:
            continue
        mid = round((seg["start_s"] + seg["end_s"]) / 2, 2)
        events.append({"creative_key": creative_key,
                       "segment": seg["segment"],
                       "start_s": seg["start_s"], "end_s": seg["end_s"],
                       "seek_s": seg["start_s"],
                       "from_pct": seg["from_pct"], "to_pct": seg["to_pct"],
                       "drop_pts": seg["drop_pts"],
                       "n_points": seg["n_points"],
                       "element": element_at(ann, mid)})
    events.sort(key=lambda e: -e["drop_pts"])
    return events


def patterns(conn, scope=None, min_drop_pts=DROP_PTS_MIN):
    """Cross-video drop patterns over the scoped population.

    scope is the shared analysis Scope (or plain filter dict):
    only creatives with at least one scoped ads row contribute.
    Returns per-creative events plus patterns aggregated by the
    element signature under each drop (slot + product/brand/cta /
    voiceover co-occurrence), with n_creatives, avg drop and
    example creatives per pattern.
    """
    from . import benchmarks
    scope = (scope if isinstance(scope, benchmarks.Scope)
             else benchmarks.Scope(scope))
    ad_cols = [c[0] for c in conn.execute(
        "SELECT * FROM ads LIMIT 0").description]
    in_scope = set()
    for v in conn.execute("SELECT * FROM ads").fetchall():
        row = dict(zip(ad_cols, v))
        if scope.match(row) and row.get("creative_key"):
            in_scope.add(row["creative_key"])
    keys = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT creative_key FROM retention").fetchall()
        } & in_scope)
    events, agg = [], {}
    for key in keys:
        try:
            _structure(conn, key)
            evs = drop_events(conn, key, min_drop_pts)
        except ValueError:
            continue
        events.extend(evs)
        for ev in evs:
            el = ev["element"]
            sig = (el["slot"], el["product_demo"], el["brand_visible"],
                   el["cta_present"], el["voiceover"])
            slot = agg.setdefault(sig, {"drops": [], "creatives": set()})
            slot["drops"].append(ev["drop_pts"])
            slot["creatives"].add(key)
    ranked = []
    for (slot, product, brand, cta, vo), data in agg.items():
        ranked.append({
            "slot": slot, "product_demo": product,
            "brand_visible": brand, "cta_present": cta,
            "voiceover": vo,
            "n_creatives": len(data["creatives"]),
            "avg_drop_pts": round(sum(data["drops"]) / len(data["drops"]), 2),
            "max_drop_pts": round(max(data["drops"]), 2),
            "examples": sorted(data["creatives"])[:5]})
    ranked.sort(key=lambda p: (-p["n_creatives"], -p["avg_drop_pts"]))
    return {"scope": scope.describe(), "n_creatives": len(keys),
            "n_events": len(events), "events": events,
            "patterns": ranked}

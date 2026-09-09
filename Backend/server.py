"""Stdlib HTTP backend + static UI. Loopback only. No secrets here."""

import argparse
import json
import os
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from creative_intel import (benchmarks, connectors, creative, export_gate,
                            ingest, media, providers, qa, replay, retention,
                            schema)

WEB_INDEX = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "Web", "Index.html"))
ASSETS_DIR = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "Web", "assets"))
BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
def _fixture_dir():
    for name in ("fixtures", "Fixtures"):
        candidate = os.path.join(BASE, name)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(BASE, "fixtures")


FIXTURES = _fixture_dir()


def connect(db_path):
    conn = sqlite3.connect(db_path)
    schema.init_db(conn)
    return conn


def send(handler, code, obj):
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


FILTER_AXES = ("platform", "vertical", "funnel", "objective",
               "market", "client", "date")


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


MAX_JSON_BYTES = 120 * 1024 * 1024


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
        va, vb = da.get(metric, 0) or 0, db.get(metric, 0) or 0
        if va == vb:
            continue
        winner = a if (va > vb) == higher_wins else b
        diffs.append("%s leads %s on %s (%s vs %s)"
                     % (winner, b if winner == a else a,
                        metric.upper(), va, vb))
    aa, ab = da.get("annotation") or {}, db.get("annotation") or {}
    for field, label in (("hook_type", "hook"), ("creator_vs_branded", "format")):
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
        top = a if da.get("cpa", 0) <= db.get("cpa", 0) else b
    elif (da.get("impressions") or 0) > 0 or (db.get("impressions") or 0) > 0:
        top = a if (da.get("ctr", 0) or 0) >= (db.get("ctr", 0) or 0) else b
    if top is None:
        diffs.append("Neither creative has delivery data yet.")
    return {"top": top, "differences": diffs or ["No measurable difference."]}


def read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        length = 0
    if not length:
        return {}
    if length > MAX_JSON_BYTES:
        raise ValueError("request body exceeds %d MB" % (
            MAX_JSON_BYTES // (1024 * 1024)))
    return json.loads(handler.rfile.read(length) or b"{}")


def apply_action(conn, action, payload, prov, media_dir=None):
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
        inserted = ingest.insert_rows(conn, rows)
        return {"inserted": inserted,
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
                          images=prepared["images"])
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
        csv_text = connectors.fetch_sheet_csv(payload.get("url", ""))
        rows, quarantined = ingest.parse_csv_report(
            csv_text, payload["platform"], "sheets")
        inserted = ingest.insert_rows(conn, rows)
        return {"inserted": inserted, "quarantined": quarantined,
                "quarantined_count": len(quarantined)}
    if action == "connect-drive":
        if not payload.get("platform"):
            raise ValueError("drive import needs a platform")
        url = connectors.drive_file_url(payload.get("url", ""))
        blob = connectors.fetch_bytes(url)
        if blob.startswith(b"PK"):
            rows, quarantined = ingest.parse_xlsx_report(
                blob, payload["platform"], "drive")
        else:
            try:
                text = blob.decode("utf-8-sig")
            except ValueError:
                raise ValueError("Drive file is neither CSV text nor .xlsx")
            if text.lstrip().lower().startswith(("<!doctype html", "<html")):
                raise ValueError("Google returned a login/confirm page: "
                                 "private Drive files need OAuth (parked)")
            rows, quarantined = ingest.parse_csv_report(
                text, payload["platform"], "drive")
        inserted = ingest.insert_rows(conn, rows)
        return {"inserted": inserted, "quarantined": quarantined,
                "quarantined_count": len(quarantined)}
    if action == "connect-meta":
        csv_text = connectors.meta_insights_csv(
            payload.get("ad_account_id", ""), payload.get("since", ""),
            payload.get("until", ""))
        rows, quarantined = ingest.parse_csv_report(csv_text, "meta", "meta-api")
        inserted = ingest.insert_rows(conn, rows)
        return {"inserted": inserted, "quarantined": quarantined,
                "quarantined_count": len(quarantined)}
    if action == "connect-tiktok":
        csv_text = connectors.tiktok_report_csv(
            payload.get("advertiser_id", ""), payload.get("start_date", ""),
            payload.get("end_date", ""))
        rows, quarantined = ingest.parse_csv_report(
            csv_text, "tiktok", "tiktok-api")
        inserted = ingest.insert_rows(conn, rows)
        return {"inserted": inserted, "quarantined": quarantined,
                "quarantined_count": len(quarantined)}
    if action == "retention":
        conn.executemany(
            "INSERT OR REPLACE INTO retention (creative_key, t_sec, retention_pct)"
            " VALUES (?, ?, ?)",
            [(payload["creative_key"], t, p) for t, p in payload["points"]])
        conn.commit()
        return {"ok": True}
    raise ValueError("unknown action %r" % action)


class Handler(BaseHTTPRequestHandler):
    db_path = "local.db"
    prov = providers.Providers()

    def log_message(self, *args):
        pass

    def _conn(self):
        return connect(self.db_path)

    def _serve_asset(self, name):
        """Serve a branding asset. Basename-only, extension allowlist,
        confined to Web/assets — no path traversal."""
        import mimetypes
        import os
        if "/" in name or "\\" in name or name.startswith("."):
            return send(self, 404, {"error": "not found"})
        if os.path.splitext(name)[1].lower() not in (
                ".png", ".svg", ".ico", ".webp"):
            return send(self, 404, {"error": "not found"})
        path = os.path.join(ASSETS_DIR, name)
        if not os.path.isfile(path):
            return send(self, 404, {"error": "not found"})
        with open(path, "rb") as f:
            body = f.read()
        ctype, _ = mimetypes.guess_type(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        if url.path.startswith("/assets/"):
            self._serve_asset(url.path[len("/assets/"):])
            return
        if url.path.startswith("/media/"):
            conn = self._conn()
            try:
                blob, mime, filename = media.load_bytes(
                    conn, _media_dir(), url.path[len("/media/"):])
            except ValueError as e:
                conn.close()
                send(self, 404, {"error": str(e)})
                return
            conn.close()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(blob)
            return
        if url.path in ("/", "/index.html"):
            with open(WEB_INDEX, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        conn = self._conn()
        try:
            # EXPERT 2 (COHORTS+COMPARE) hook: appended routes below; ingest/load_fixtures untouched.
            if expert2_dispatch_get(self, conn, url, q):
                return
            if url.path == "/api/health":
                send(self, 200, {"ok": True, "provider_mode": self.prov.mode,
                                 "keys": providers.key_status(),
                                 "providers": providers.provider_matrix()})
            elif url.path == "/api/campaigns":
                send(self, 200, benchmarks.benchmark(
                    conn, "campaign", _filters_from_query(q)))
            elif url.path == "/api/benchmarks":
                send(self, 200, benchmarks.benchmark(
                    conn, q.get("group_by", ["hook_type"])[0],
                    _filters_from_query(q)))
            elif url.path == "/api/creatives":
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
                send(self, 200, kept)
            elif url.path == "/api/retention":
                key = q.get("creative_key", [""])[0]
                send(self, 200, retention.join_segments(conn, key))
            elif url.path == "/api/compare":
                from creative_intel import benchmarks as _bench2
                a, b = q.get("a", [""])[0], q.get("b", [""])[0]
                scope = _bench2.Scope.from_query(q)
                ad_cols = [c[0] for c in conn.execute(
                    "SELECT * FROM ads LIMIT 0").description]
                out = {}
                for key in (a, b):
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
                out["why"] = _creative_why(a, b, out.get(a, {}), out.get(b, {}))
                out["scope"] = scope.describe()
                send(self, 200, out)
            elif url.path == "/api/retention/patterns":
                from creative_intel import benchmarks as _bench3
                send(self, 200, retention.patterns(
                    conn, _bench3.Scope.from_query(q)))
            elif url.path == "/api/replay":
                send(self, 200, replay.history(conn))
            elif url.path == "/api/reviews":
                send(self, 200, qa.list_reviews(conn))
            else:
                send(self, 404, {"error": "not found"})
        except (ValueError, export_gate.ExportBlocked) as e:
            send(self, 409, {"error": str(e)})
        finally:
            conn.close()

    def do_POST(self, log_action=True):
        url = urllib.parse.urlparse(self.path)
        payload = read_json(self)
        conn = self._conn()
        try:
            # EXPERT 2 (COHORTS+COMPARE) hook: appended routes below; ingest/load_fixtures untouched.
            if expert2_dispatch_post(self, conn, url, payload):
                return
            if url.path == "/api/ingest":
                action = "ingest"
            elif url.path == "/api/media/upload":
                action = "media-upload"
            elif url.path == "/api/connect/drive":
                action = "connect-drive"
            elif url.path == "/api/connect/sheets":
                action = "connect-sheets"
            elif url.path == "/api/connect/meta":
                action = "connect-meta"
            elif url.path == "/api/connect/tiktok":
                action = "connect-tiktok"
            elif url.path == "/api/pipeline/run":
                action = "pipeline"
            elif url.path == "/api/retention":
                action = "retention"
            elif url.path == "/api/ask":
                live = (self.prov.llm if getattr(
                    self.prov, "mode", "mock") == "live" else None)
                from creative_intel import benchmarks as _bench4
                send(self, 200, qa.answer(
                    conn, payload.get("question", ""), llm=live,
                    scope=_bench4.Scope.from_payload(payload)))
                return
            elif url.path == "/api/reviews/mark":
                pending = qa.mark_reviewed(conn, int(payload["review_id"]))
                send(self, 200, {"ok": True, "pending": pending})
                return
            elif url.path == "/api/export":
                try:
                    export_gate.check_reviews(conn)
                    result = export_gate.build_one_pager(
                        conn, payload.get("creative_keys", []),
                        benchmarks.benchmark(conn, "hook_type"),
                        override=bool(payload.get("override")))
                except export_gate.ExportBlocked as e:
                    send(self, 409, {"error": str(e), "missing": e.missing})
                    return
                replay.log(conn, "export", {"creative_keys": payload.get(
                    "creative_keys", []), "override": bool(payload.get("override"))})
                send(self, 200, result)
                return
            elif url.path == "/api/replay/run":
                hist = replay.history(conn)
                mem = sqlite3.connect(":memory:")
                schema.init_db(mem)
                n = 0
                for entry in hist:
                    if entry["action"] in ("export", "report-override"):
                        continue
                    apply_action(mem, entry["action"], entry["payload"], self.prov)
                    n += 1
                live = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
                replayed = mem.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
                mem.close()
                send(self, 200, {"replayed": n, "live_ads": live,
                                 "replayed_ads": replayed,
                                 "matches_live": live == replayed})
                return
            elif url.path.startswith("/api/creatives/") and url.path.endswith("/verify"):
                key = urllib.parse.unquote(url.path[len("/api/creatives/"):-len("/verify")])
                payload = {"creative_key": key}
                action = "verify"
            elif url.path.startswith("/api/creatives/") and url.path.endswith("/annotate"):
                key = urllib.parse.unquote(url.path[len("/api/creatives/"):-len("/annotate")])
                payload = {"creative_key": key, "annotation": payload.get("annotation", {})}
                action = "annotate"
            else:
                send(self, 404, {"error": "not found"})
                return
            result = apply_action(conn, action, payload, self.prov)
            if action != "media-upload":
                # Media bytes stay out of the replay log (size + portability).
                replay.log(conn, action, payload)
            send(self, 200, result)
        except (ValueError, export_gate.ExportBlocked) as e:
            send(self, 409, {"error": str(e)})
        finally:
            conn.close()


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE, "Data", "local.db"))
    ap.add_argument("--port", type=int, default=4321)
    ap.add_argument("--load-fixture", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    if args.load_fixture:
        print("fixture rows: %d" % load_fixtures(args.db))
        return
    Handler.db_path = args.db
    srv = HTTPServer(("127.0.0.1", args.port), Handler)
    print("Creative Intelligence on http://127.0.0.1:%d" % args.port)
    srv.serve_forever()


# === EXPERT 2 (COHORTS+COMPARE) APPENDED ROUTES ===
"""Multi-campaign compare, cohort benchmark, and report-generation routes.

New endpoints (all JSON):
  GET  /api/compare/campaigns?campaigns=A,B&rank_by=cpa
  GET  /api/cohorts                                   list saved cohorts
  POST /api/cohorts          {name, filters}          save a cohort
  GET  /api/cohorts/build?name=X&metric=cpa           build saved/ad-hoc cohort
  POST /api/report           {campaigns, kpis, benchmark, format}
The legacy GET /api/compare?a=&b= and /api/benchmarks paths above are unchanged.
"""


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
                                 filters=payload.get("filters"))
    if override:
        replay.log(conn, "report-override",
                   {"campaigns": campaigns, "format": fmt,
                    "kpis": kpis, "override": True})
    return result


def expert2_dispatch_get(handler, conn, url, query):
    """Handle EXPERT 2 GET routes. Returns True when the request was served."""
    if url.path == "/api/compare/campaigns":
        try:
            send(handler, 200, expert2_compare_route(conn, query))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
        return True
    if url.path == "/api/cohorts":
        from creative_intel import cohorts as _cohorts
        try:
            send(handler, 200, _cohorts.list_cohorts(conn))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
        return True
    if url.path == "/api/cohorts/build":
        try:
            send(handler, 200, expert2_cohort_build_route(conn, query))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
        return True
    return False


def expert2_dispatch_post(handler, conn, url, payload):
    """Handle EXPERT 2 POST routes. Returns True when the request was served."""
    if url.path == "/api/cohorts":
        from creative_intel import cohorts as _cohorts
        try:
            result = _cohorts.save_cohort(conn, payload.get("name", ""),
                                          payload.get("filters", {}))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
            return True
        send(handler, 200, result)
        return True
    if url.path == "/api/compare/campaigns":
        try:
            # POST callers scope via the filters object; fold it into
            # the pseudo-query so the comparison runs once, scoped.
            pseudo = {"campaigns": [",".join(
                payload.get("campaigns", []) or [])],
                "rank_by": [payload.get("rank_by", "cpa")]}
            for key, vals in ((payload.get("filters") or {}).items()):
                pseudo[key] = (list(vals) if isinstance(vals, list)
                               else [vals])
            send(handler, 200, expert2_compare_route(conn, pseudo))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
        return True
    if url.path == "/api/report":
        try:
            send(handler, 200, expert2_report_route(conn, payload))
        except ValueError as e:
            send(handler, 409, {"error": str(e)})
        return True
    return False


if __name__ == "__main__":
    main()

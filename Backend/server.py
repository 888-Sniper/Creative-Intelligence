"""Stdlib HTTP backend + static UI. Loopback only. No secrets here."""

import argparse
import json
import os
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from creative_intel import (benchmarks, creative, export_gate, ingest,
                            providers, qa, replay, retention, schema)

WEB_INDEX = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "Web", "Index.html"))
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


def read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except ValueError:
        length = 0
    if not length:
        return {}
    return json.loads(handler.rfile.read(length) or b"{}")


def apply_action(conn, action, payload, prov):
    if action == "ingest":
        if not isinstance(payload.get("csv"), str) or not payload.get("platform"):
            raise ValueError("ingest needs csv text and platform")
        rows, quarantined = ingest.parse_csv_report(
            payload["csv"], payload["platform"],
            payload.get("source", "upload"))
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
        return creative.run_pipeline(conn, payload["creative_key"], prov)
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

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
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
                send(self, 200, benchmarks.benchmark(conn, "campaign"))
            elif url.path == "/api/benchmarks":
                send(self, 200, benchmarks.benchmark(
                    conn, q.get("group_by", ["hook_type"])[0]))
            elif url.path == "/api/creatives":
                cols = ["creative_key", "platform", "name", "duration_s",
                        "status", "transcript"]
                rows = [dict(zip(cols, r)) for r in conn.execute(
                    "SELECT creative_key, platform, name, duration_s, status,"
                    " transcript FROM creatives")]
                for r in rows:
                    ann = conn.execute(
                        "SELECT annotation_json FROM annotations WHERE creative_key=?",
                        (r["creative_key"],)).fetchone()
                    r["annotation"] = json.loads(ann[0]) if ann else None
                send(self, 200, rows)
            elif url.path == "/api/retention":
                key = q.get("creative_key", [""])[0]
                send(self, 200, retention.join_segments(conn, key))
            elif url.path == "/api/compare":
                a, b = q.get("a", [""])[0], q.get("b", [""])[0]
                out = {}
                for key in (a, b):
                    rows = conn.execute("SELECT spend, impressions, clicks, conversions"
                                        " FROM ads WHERE creative_key=?", (key,)).fetchall()
                    spend = sum(r[0] for r in rows)
                    impr = sum(r[1] for r in rows)
                    clicks = sum(r[2] for r in rows)
                    conv = sum(r[3] for r in rows)
                    ann = conn.execute("SELECT annotation_json FROM annotations"
                                       " WHERE creative_key=?", (key,)).fetchone()
                    out[key] = {"spend": spend,
                                "ctr": round(clicks / impr, 4) if impr else 0.0,
                                "cpa": round(spend / conv, 2) if conv else 0.0,
                                "annotation": json.loads(ann[0]) if ann else None}
                send(self, 200, out)
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
            elif url.path == "/api/pipeline/run":
                action = "pipeline"
            elif url.path == "/api/retention":
                action = "retention"
            elif url.path == "/api/ask":
                send(self, 200, qa.answer(conn, payload.get("question", "")))
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
                    if entry["action"] == "export":
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
    return _bench.compare_campaigns(
        conn, campaigns or None, rank_by=rank_by)


def expert2_cohort_build_route(conn, query):
    from creative_intel import cohorts as _cohorts
    metric = (query.get("metric", ["cpa"])[0] or "cpa").lower()
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
    campaigns = payload.get("campaigns") or None
    kpis = payload.get("kpis") or ["cpa", "ctr"]
    benchmark_sel = payload.get("benchmark")
    fmt = payload.get("format", "one-pager")
    return _bench.build_report(conn, campaigns, kpis, benchmark_sel, fmt)


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
            send(handler, 200, expert2_compare_route(
                conn, {"campaigns": [",".join(payload.get("campaigns", []) or [])],
                       "rank_by": [payload.get("rank_by", "cpa")]}))
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

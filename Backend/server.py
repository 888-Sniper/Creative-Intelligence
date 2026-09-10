"""Stdlib HTTP backend + static UI. Loopback only. No secrets here."""

import argparse
import json
import os
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from creative_intel import (auth, benchmarks, creative, export_gate,
                            ingest, media, providers, qa, replay, retention,
                            schema, sync)
from ci_backend.actions import (  # noqa: E402
    ASSETS_DIR, BASE, FIXTURES, WEB_INDEX, _creative_why, _csv_param,
    _filters_from_query, _fixture_dir, _media_dir, _multi_why,
    _slot_set, _span_start, apply_action, build_compare,
    build_creatives_list, connect, expert2_cohort_build_route,
    expert2_compare_route, expert2_report_route, list_views, load_fixtures,
    save_view)
from ci_backend.actions import (  # noqa: E402
    FILTER_AXES, VIEW_KEYS, VIEW_KPIS, VIEW_RANKS)


def send(handler, code, obj):
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_cookie(handler, code, obj, cookie=None):
    """JSON response with an optional Set-Cookie (session issue/clear)."""
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    if cookie:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()
    handler.wfile.write(body)


def redirect_home(handler, cookie=None, error=""):
    """OAuth landing: 302 to /, session via cookie only (never the URL)."""
    target = "/"
    if error:
        target = "/?auth_error=" + urllib.parse.quote(error[:200])
    handler.send_response(302)
    handler.send_header("Location", target)
    if cookie:
        handler.send_header("Set-Cookie", cookie)
    handler.end_headers()


def _guard(handler, conn, admin=False):
    """Default-deny gate. Returns (True, employee-or-None).

    Sends 401 (no/expired session) or 403 (wrong status/role) and
    returns (False, None) when denied. There is no setup bypass:
    zero employees means login is required, and only the configured
    bootstrap-admin identity can become the first admin.
    """
    if admin:
        return _guard_admin(handler, conn)
    try:
        emp, _gate = auth.authorize(
            conn, auth.token_from_headers(handler.headers))
    except auth.Denied as exc:
        send(handler, 401 if exc.gate == "login" else 403,
             {"error": str(exc), "gate": exc.gate})
        return False, None
    return True, emp


def _login_verified(conn, identity):
    """Email-grant login: verified WorkOS identity only, then session.

    Returns (token, employee, gate) where gate mirrors /me so the
    frontend lands on app/pending/suspended without a second call.
    """
    if not identity.get("workos_user_id") or not identity.get("verified"):
        raise auth.AuthError("WorkOS did not return a verified identity.")
    token, emp, _created = auth.login_identity(conn, identity)
    gate = "app" if emp.get("status") == "active" else emp.get("status")
    return token, emp, gate


def _guard_admin(handler, conn):
    """Admin gate: live session + active employee + admin role."""
    try:
        emp, _gate = auth.authorize(
            conn, auth.token_from_headers(handler.headers))
    except auth.Denied as exc:
        send(handler, 401 if exc.gate == "login" else 403,
             {"error": str(exc), "gate": exc.gate})
        return False, None
    if emp.get("role") != "admin":
        send(handler, 403, {"error": "Administrator access required.",
                            "gate": "forbidden"})
        return False, None
    return True, emp




MAX_JSON_BYTES = 120 * 1024 * 1024




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
                # Media rides cookies (<video> tags can't set headers):
                # live session for an active employee, like every API.
                ok, _emp = _guard(self, conn)
                if not ok:
                    conn.close()
                    return
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
            if url.path == "/api/auth/me":
                send(self, 200, auth.me(
                    conn, auth.token_from_headers(self.headers)))
                return
            if url.path == "/api/auth/accounts":
                token = auth.token_from_headers(self.headers)
                if auth.valid_session(conn, token) is None:
                    send(self, 401, {"error": "Sign in to continue.",
                                     "gate": "login"})
                    return
                send(self, 200, {"accounts": auth.list_accounts(conn)})
                return
            if url.path == "/api/auth/callback":
                try:
                    identity = auth.finish_oauth(
                        conn, q.get("code", [""])[0],
                        q.get("state", [""])[0])
                    token, _emp, _created = auth.login_identity(
                        conn, identity)
                except (auth.AuthError, auth.Denied) as e:
                    redirect_home(self, error=str(e))
                    return
                redirect_home(self, auth.session_cookie(token))
                return
            if url.path.startswith("/api/admin/"):
                ok, admin = _guard_admin(self, conn)
                if not ok:
                    return
                if url.path == "/api/admin/employees":
                    send(self, 200, {"employees": auth.admin_list(
                        conn, q.get("search", [""])[0],
                        q.get("filter", [""])[0])})
                    return
                if url.path == "/api/admin/audit":
                    send(self, 200, {"events": auth.admin_audit_list(
                        conn, q.get("limit", ["100"])[0])})
                    return
                parts = url.path[len("/api/admin/employees/"):].split("/")
                if len(parts) == 1 and parts[0]:
                    emp = auth.get_employee(conn, urllib.parse.unquote(
                        parts[0]))
                    if emp is None:
                        send(self, 404, {"error": "Employee not found."})
                    else:
                        send(self, 200, {"employee":
                                         auth.public_employee(emp)})
                    return
                send(self, 404, {"error": "not found"})
                return
            # EXPERT 2 (COHORTS+COMPARE) hook: appended routes below; ingest/load_fixtures untouched.
            if url.path.startswith("/api/") and url.path != "/api/health":
                ok, _emp = _guard(self, conn)
                if not ok:
                    return
            if expert2_dispatch_get(self, conn, url, q):
                return
            if url.path == "/api/health":
                send(self, 200, {"ok": True, "provider_mode": self.prov.mode,
                                 "keys": providers.key_status(),
                                 "providers": providers.provider_matrix()})
            elif url.path == "/api/campaigns":
                # Same shared Scope as every other surface: a
                # Campaign=CampA filter scopes Overview KPIs too, not
                # just the library/Ask/reports.
                send(self, 200, benchmarks.benchmark(
                    conn, "campaign",
                    benchmarks.Scope.from_query(q).normalized()))
            elif url.path == "/api/campaigns/recommendations":
                name = q.get("name", [""])[0]
                if not name:
                    raise ValueError(
                        "recommendations need a campaign name")
                rank_by = (q.get("rank_by", ["cpa"])[0] or "cpa").lower()
                # Pass the Scope itself, not normalized(): normalized()
                # folds project into include_projects, which a fresh
                # Scope() would silently drop — analysing all projects.
                send(self, 200, benchmarks.campaign_recommendations(
                    conn, name, benchmarks.Scope.from_query(q), rank_by))
            elif url.path == "/api/benchmarks":
                send(self, 200, benchmarks.benchmark(
                    conn, q.get("group_by", ["hook_type"])[0],
                    benchmarks.Scope.from_query(q).normalized()))
            elif url.path == "/api/creatives":
                send(self, 200, build_creatives_list(conn, q))
            elif url.path == "/api/retention":
                key = q.get("creative_key", [""])[0]
                send(self, 200, retention.join_segments(conn, key))
            elif url.path == "/api/compare":
                send(self, 200, build_compare(conn, q))
            elif url.path == "/api/retention/patterns":
                from creative_intel import benchmarks as _bench3
                send(self, 200, retention.patterns(
                    conn, _bench3.Scope.from_query(q)))
            elif url.path == "/api/retention/curve":
                key = q.get("creative_key", [""])[0]
                send(self, 200, retention.curve(conn, key))
            elif url.path == "/api/compare/periods":
                from creative_intel import benchmarks as _bench6
                # a_from/a_to/b_from/b_to name the windows; every
                # other axis scopes both windows identically.
                scope = _bench6.Scope.from_query(
                    q, ignore=("a_from", "a_to", "b_from", "b_to",
                               "label_a", "label_b"))
                send(self, 200, _bench6.compare_periods(
                    conn, q.get("a_from", [""])[0], q.get("a_to", [""])[0],
                    q.get("b_from", [""])[0], q.get("b_to", [""])[0],
                    filters=scope,
                    label_a=q.get("label_a", ["Period A"])[0] or "Period A",
                    label_b=q.get("label_b", ["Period B"])[0] or "Period B"))
            elif url.path == "/api/replay":
                send(self, 200, replay.history(conn))
            elif url.path == "/api/sync/status":
                send(self, 200, sync.status(conn))
            elif url.path == "/api/views":
                send(self, 200, list_views(conn))
            elif url.path == "/api/reviews":
                send(self, 200, qa.list_reviews(conn))
            else:
                send(self, 404, {"error": "not found"})
        except (ValueError, export_gate.ExportBlocked, auth.AuthError) as e:
            send(self, 409, {"error": str(e)})
        finally:
            conn.close()

    def do_POST(self, log_action=True):
        url = urllib.parse.urlparse(self.path)
        payload = read_json(self)
        conn = self._conn()
        try:
            if url.path == "/api/auth/oauth/start":
                port = self.server.server_address[1]
                out = auth.start_oauth(
                    conn, payload.get("provider", ""),
                    auth.redirect_uri(port))
                send(self, 200, out)
                return
            if url.path == "/api/auth/oauth/finish":
                try:
                    identity = auth.finish_oauth(
                        conn, payload.get("code", ""),
                        payload.get("state", ""))
                    token, emp, _created = auth.login_identity(
                        conn, identity)
                except (auth.AuthError, auth.Denied) as e:
                    send(self, 409, {"error": str(e)})
                    return
                send_cookie(self, 200,
                            {"ok": True, "gate": "app"
                             if emp.get("status") == "active"
                             else emp.get("status"),
                             "employee": auth.public_employee(emp)},
                            auth.session_cookie(token))
                return
            if url.path == "/api/auth/email/signin":
                identity = auth.public_identity(
                    auth.authenticate_password(
                        payload.get("email", ""), payload.get("password", "")),
                    provider="email")
                token, emp, gate = _login_verified(conn, identity)
                send_cookie(self, 200, {"ok": True, "gate": gate,
                                        "employee":
                                        auth.public_employee(emp)},
                            auth.session_cookie(token))
                return
            if url.path == "/api/auth/email/code":
                auth.send_magic_code(payload.get("email", ""))
                send(self, 200, {"ok": True})
                return
            if url.path == "/api/auth/email/code/signin":
                identity = auth.public_identity(
                    auth.authenticate_magic_code(
                        payload.get("email", ""), payload.get("code", "")),
                    provider="email")
                token, emp, gate = _login_verified(conn, identity)
                send_cookie(self, 200, {"ok": True, "gate": gate,
                                        "employee":
                                        auth.public_employee(emp)},
                            auth.session_cookie(token))
                return
            if url.path == "/api/auth/email/reset":
                auth.send_password_reset(payload.get("email", ""))
                send(self, 200, {"ok": True})
                return
            if url.path == "/api/auth/password/reset":
                auth.reset_password(payload.get("token", ""),
                                    payload.get("password", ""))
                send(self, 200, {"ok": True})
                return
            if url.path == "/api/auth/logout":
                auth.destroy_session(
                    conn, auth.token_from_headers(self.headers))
                send_cookie(self, 200, {"ok": True}, auth.clear_cookie())
                return
            if url.path == "/api/auth/switch":
                token = auth.token_from_headers(self.headers)
                if auth.valid_session(conn, token) is None:
                    send(self, 401, {"error": "Sign in to continue.",
                                     "gate": "login"})
                    return
                target = auth.get_employee(conn, payload.get("employee_id",
                                                             ""))
                if target is None or not auth.has_live_session(
                        conn, target["id"]):
                    send(self, 404, {"error": "Sign in with that"
                                     " account first."})
                    return
                fresh = auth.create_session(conn, target["id"],
                                            target.get("workos_user_id")
                                            or "")
                send_cookie(self, 200,
                            {"ok": True,
                             "employee": auth.public_employee(target)},
                            auth.session_cookie(fresh))
                return
            if url.path.startswith("/api/admin/"):
                ok, admin = _guard_admin(self, conn)
                if not ok:
                    return
                if url.path == "/api/admin/employees":
                    emp = auth.admin_create(
                        conn, admin["id"], payload.get("email", ""),
                        payload.get("first_name", ""),
                        payload.get("last_name", ""),
                        payload.get("role", "employee"))
                    send(self, 200, {"employee":
                                     auth.public_employee(emp)})
                    return
                parts = url.path[len("/api/admin/employees/"):].split("/")
                if len(parts) == 2 and parts[0]:
                    target = urllib.parse.unquote(parts[0])
                    verb = parts[1]
                    if verb in ("approve", "suspend", "reactivate",
                                "revoke"):
                        moves = {"approve": ("active", "EMPLOYEE_APPROVED"),
                                 "suspend": ("suspended",
                                             "EMPLOYEE_SUSPENDED"),
                                 "reactivate": ("active",
                                                "EMPLOYEE_REACTIVATED"),
                                 "revoke": ("revoked", "EMPLOYEE_REVOKED")}
                        status, action = moves[verb]
                        emp = auth.admin_set_status(
                            conn, admin["id"], target, status, action)
                        send(self, 200, {"employee":
                                         auth.public_employee(emp)})
                        return
                    if verb == "role":
                        emp = auth.admin_set_role(
                            conn, admin["id"], target,
                            payload.get("role", ""))
                        send(self, 200, {"employee":
                                         auth.public_employee(emp)})
                        return
                send(self, 404, {"error": "not found"})
                return
            if url.path.startswith("/api/"):
                ok, _emp = _guard(self, conn)
                if not ok:
                    return
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
            elif url.path == "/api/sync/run":
                action = "sync-now"
            elif url.path == "/api/pipeline/run":
                action = "pipeline"
            elif url.path == "/api/retention":
                action = "retention"
            elif url.path == "/api/views":
                action = "save-view"
            elif url.path == "/api/views/delete":
                action = "delete-view"
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
        except (ValueError, export_gate.ExportBlocked, auth.AuthError) as e:
            send(self, 409, {"error": str(e)})
        finally:
            conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE, "Data", "local.db"))
    ap.add_argument("--port", type=int, default=4321)
    ap.add_argument("--load-fixture", action="store_true")
    ap.add_argument("--sync-every", type=int, default=0,
                    help="re-run saved connector sync jobs every N seconds"
                    " (0 disables the scheduler)")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    if args.load_fixture:
        print("fixture rows: %d" % load_fixtures(args.db))
        return
    Handler.db_path = args.db
    if args.sync_every > 0:
        import threading
        stop = threading.Event()
        thread = threading.Thread(
            target=sync.daemon,
            args=(args.db, args.sync_every, stop), daemon=True)
        thread.start()
        print("sync scheduler: every %d seconds" % args.sync_every)
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

"""WorkOS login + admin-controlled employee access journeys.

Stdlib port of Nextly's auth test approach (stub the WorkOS call,
drive the real store/routes/cookies end to end). Covers the goal's
30 acceptance items; dependency substitutions (unittest for pytest,
static-HTML assertions for Vitest/Playwright, schema.migrate for
Alembic, urllib for httpx) are documented, not hidden.
"""

import json
import os
import re
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import auth, schema

ID_A = {"workos_user_id": "w-ada", "email": "ada@foap.test",
        "first_name": "Ada", "last_name": "L", "avatar_url": "",
        "verified": True, "provider": "google"}
ID_B = {"workos_user_id": "w-bo", "email": "bo@foap.test",
        "first_name": "Bo", "last_name": "B", "avatar_url": "",
        "verified": True, "provider": "github"}


def _conn():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


class AuthCase(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        os.environ["CREATIVE_INTEL_WORKOS_CLIENT_ID"] = "client_test"
        os.environ["CREATIVE_INTEL_KEY_WORKOS"] = "sk_test_key"
        os.environ.pop("CREATIVE_INTEL_ADMIN_EMAIL", None)
        os.environ.pop("CREATIVE_INTEL_BASE_WORKOS", None)
        self._patched = []

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)
        for mod, name, orig in self._patched:
            setattr(mod, name, orig)

    def _stub_exchange(self, identity):
        orig = auth.authenticate_code

        def fake(code, verifier):
            assert code == "auth_code", code
            self._seen_verifier = verifier
            return {"user": {
                "id": identity["workos_user_id"],
                "email": identity["email"],
                "email_verified": True,
                "first_name": identity["first_name"],
                "last_name": identity["last_name"],
                "profile_picture_url": "",
            }}

        auth.authenticate_code = fake
        self._patched.append((auth, "authenticate_code", orig))

    def _oauth_login(self, conn, identity, provider="google"):
        """Full start→finish→session round-trip with a stubbed code."""
        self._stub_exchange(identity)
        started = auth.start_oauth(conn, provider)
        row = conn.execute(
            "SELECT verifier FROM auth_pending WHERE state=?",
            (started["state"],)).fetchone()
        self.assertTrue(row[0])  # PKCE verifier persisted server-side
        ident = auth.finish_oauth(conn, "auth_code", started["state"])
        self.assertEqual(ident["workos_user_id"],
                         identity["workos_user_id"])
        return auth.login_identity(conn, ident)


class OAuthFlowTest(AuthCase):
    def test_start_url_contents(self):
        conn = _conn()
        try:
            out = auth.start_oauth(conn, "google")
            url = out["url"]
            self.assertIn("client_test", url)
            self.assertIn("GoogleOAuth", url)
            self.assertIn("code_challenge=", url)
            self.assertIn("code_challenge_method=S256", url)
            self.assertIn("state=" + out["state"], url)
            self.assertNotIn("sk_test_key", url)
        finally:
            conn.close()

    def test_start_rejects_unknown_provider(self):
        conn = _conn()
        try:
            with self.assertRaises(auth.AuthError):
                auth.start_oauth(conn, "facebook")
        finally:
            conn.close()

    def test_all_four_providers(self):
        # Goal items 2-5: google/apple/github/microsoft succeed.
        for provider, tag in (("google", "GoogleOAuth"),
                              ("apple", "AppleOAuth"),
                              ("github", "GitHubOAuth"),
                              ("microsoft", "MicrosoftOAuth")):
            conn = _conn()
            try:
                out = auth.start_oauth(conn, provider)
                self.assertIn(tag, out["url"])
            finally:
                conn.close()

    def test_state_single_use_and_expiry(self):
        # Goal items 6 + 27: replayed/unknown states fail closed.
        conn = _conn()
        try:
            self._stub_exchange(ID_A)
            started = auth.start_oauth(conn, "google")
            ident = auth.finish_oauth(conn, "auth_code", started["state"])
            auth.login_identity(conn, ident)
            with self.assertRaises(auth.AuthError):
                auth.finish_oauth(conn, "auth_code", started["state"])
            with self.assertRaises(auth.AuthError):
                auth.finish_oauth(conn, "auth_code", "nope")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
                1)
        finally:
            conn.close()

    def test_pending_state_expires(self):
        conn = _conn()
        try:
            started = auth.start_oauth(conn, "google")
            conn.execute("UPDATE auth_pending SET created_at=?"
                         " WHERE state=?",
                         ("2000-01-01T00:00:00+00:00", started["state"]))
            conn.commit()
            with self.assertRaises(auth.AuthError):
                auth.finish_oauth(conn, "auth_code", started["state"])
        finally:
            conn.close()

    def test_unverified_identity_refused(self):
        conn = _conn()
        try:
            orig = auth.authenticate_code
            auth.authenticate_code = lambda c, v: {"user": {
                "id": "w-x", "email": "x@foap.test"}}
            self._patched.append((auth, "authenticate_code", orig))
            started = auth.start_oauth(conn, "google")
            with self.assertRaises(auth.AuthError):
                auth.finish_oauth(conn, "auth_code", started["state"])
        finally:
            conn.close()


class EmployeeGateTest(AuthCase):
    def test_unknown_user_becomes_pending(self):
        # Goal items 7-8.
        conn = _conn()
        try:
            token, emp, created = self._oauth_login(conn, ID_A)
            self.assertTrue(created)
            self.assertEqual(emp["status"], "pending")
            with self.assertRaises(auth.Denied) as ctx:
                auth.authorize(conn, token)
            self.assertEqual(ctx.exception.gate, "pending")
            me = auth.me(conn, token)
            self.assertTrue(me["authenticated"])
            self.assertEqual(me["gate"], "pending")
            self.assertFalse(me["is_admin"])
        finally:
            conn.close()

    def test_bootstrap_admin(self):
        os.environ["CREATIVE_INTEL_ADMIN_EMAIL"] = "ada@foap.test"
        conn = _conn()
        try:
            _tok, emp, _c = self._oauth_login(conn, ID_A)
            self.assertEqual(emp["role"], "admin")
            self.assertEqual(emp["status"], "active")
            # Second user is NOT bootstrapped.
            _t2, emp2, _c2 = self._oauth_login(conn, ID_B)
            self.assertEqual(emp2["role"], "employee")
            self.assertEqual(emp2["status"], "pending")
        finally:
            conn.close()

    def test_no_bootstrap_without_env(self):
        conn = _conn()
        try:
            _tok, emp, _c = self._oauth_login(conn, ID_A)
            self.assertEqual(emp["role"], "employee")
            self.assertEqual(emp["status"], "pending")
        finally:
            conn.close()

    def test_preadded_email_links_no_dupe(self):
        # Goal item 28.
        conn = _conn()
        try:
            admin = auth.admin_create(conn, "root", "ada@foap.test",
                                      "Ada", "L", "employee")
            self.assertEqual(admin["status"], "active")
            self.assertFalse(admin["workos_user_id"])
            _tok, emp, created = self._oauth_login(conn, ID_A)
            self.assertFalse(created)
            self.assertEqual(emp["id"], admin["id"])
            self.assertEqual(emp["workos_user_id"], "w-ada")
            self.assertEqual(emp["status"], "active")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
                1)
        finally:
            conn.close()

    def test_approve_suspend_reactivate_revoke(self):
        # Goal items 10-14.
        conn = _conn()
        try:
            token, emp, _c = self._oauth_login(conn, ID_A)
            with self.assertRaises(auth.Denied):
                auth.authorize(conn, token)
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_APPROVED")
            _emp, gate = auth.authorize(conn, token)
            self.assertEqual(gate, "app")
            auth.admin_set_status(conn, "root", emp["id"], "suspended",
                                  "EMPLOYEE_SUSPENDED")
            # Old session is dead: re-authenticating lands on Suspended.
            with self.assertRaises(auth.Denied) as ctx:
                auth.authorize(conn, token)
            self.assertEqual(ctx.exception.gate, "login")
            token2, _e2, _c2 = auth.login_identity(conn, ID_A)
            with self.assertRaises(auth.Denied) as ctx:
                auth.authorize(conn, token2)
            self.assertEqual(ctx.exception.gate, "suspended")
            self.assertEqual(auth.me(conn, token2)["gate"], "suspended")
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_REACTIVATED")
            _emp, gate = auth.authorize(conn, token2)
            self.assertEqual(gate, "app")
            auth.admin_set_status(conn, "root", emp["id"], "revoked",
                                  "EMPLOYEE_REVOKED")
            with self.assertRaises(auth.Denied) as ctx:
                auth.authorize(conn, token2)
            self.assertEqual(ctx.exception.gate, "login")
            token3, _e3, _c3 = auth.login_identity(conn, ID_A)
            with self.assertRaises(auth.Denied) as ctx:
                auth.authorize(conn, token3)
            self.assertEqual(ctx.exception.gate, "revoked")
        finally:
            conn.close()

    def test_suspend_destroys_live_sessions(self):
        conn = _conn()
        try:
            token, emp, _c = self._oauth_login(conn, ID_A)
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_APPROVED")
            auth.authorize(conn, token)
            auth.admin_set_status(conn, "root", emp["id"], "suspended",
                                  "EMPLOYEE_SUSPENDED")
            self.assertIsNone(auth._session_row(conn, token))
        finally:
            conn.close()

    def test_illegal_transitions_rejected(self):
        conn = _conn()
        try:
            _tok, emp, _c = self._oauth_login(conn, ID_A)
            with self.assertRaises(auth.AuthError):
                auth.admin_set_status(conn, "root", emp["id"], "suspended",
                                      "EMPLOYEE_SUSPENDED")
            auth.admin_set_status(conn, "root", emp["id"], "revoked",
                                  "EMPLOYEE_REVOKED")
            with self.assertRaises(auth.AuthError):
                auth.admin_set_status(conn, "root", emp["id"], "active",
                                      "EMPLOYEE_REACTIVATED")
        finally:
            conn.close()

    def test_authorization_rechecked_every_call(self):
        # Goal item 21.
        conn = _conn()
        try:
            token, emp, _c = self._oauth_login(conn, ID_A)
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_APPROVED")
            auth.authorize(conn, token)
            conn.execute("UPDATE employees SET status='revoked'"
                         " WHERE id=?", (emp["id"],))
            conn.commit()
            with self.assertRaises(auth.Denied):
                auth.authorize(conn, token)
        finally:
            conn.close()

    def test_logout_kills_session(self):
        # Goal item 19.
        conn = _conn()
        try:
            token, emp, _c = self._oauth_login(conn, ID_A)
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_APPROVED")
            auth.authorize(conn, token)
            auth.destroy_session(conn, token)
            with self.assertRaises(auth.Denied):
                auth.authorize(conn, token)
            self.assertEqual(auth.me(conn, token)["gate"], "login")
        finally:
            conn.close()

    def test_audit_trail(self):
        # Goal item 26.
        conn = _conn()
        try:
            _tok, emp, _c = self._oauth_login(conn, ID_A)
            auth.admin_create(conn, "root", "c@foap.test", role="employee")
            auth.admin_set_status(conn, "root", emp["id"], "active",
                                  "EMPLOYEE_APPROVED")
            auth.admin_set_role(conn, "root", emp["id"], "admin")
            actions = [e["action"] for e in auth.admin_audit_list(conn)]
            for want in ("EMPLOYEE_CREATED", "EMPLOYEE_APPROVED",
                         "ROLE_CHANGED"):
                self.assertIn(want, actions)
            row = [e for e in auth.admin_audit_list(conn)
                   if e["action"] == "EMPLOYEE_APPROVED"][0]
            self.assertEqual((row["target_id"], row["admin_id"],
                              row["prev_value"], row["new_value"]),
                             (emp["id"], "root", "pending", "active"))
            self.assertTrue(row["created_at"])
        finally:
            conn.close()

    def test_multi_account_isolation(self):
        # Goal items 22-25.
        conn = _conn()
        try:
            tok_a, emp_a, _c = self._oauth_login(conn, ID_A)
            tok_b, emp_b, _c2 = self._oauth_login(conn, ID_B)
            auth.admin_set_status(conn, "root", emp_a["id"], "active",
                                  "EMPLOYEE_APPROVED")
            auth.admin_set_role(conn, "root", emp_a["id"], "admin")
            # B stays pending: A's grant never leaks.
            with self.assertRaises(auth.Denied):
                auth.authorize(conn, tok_b)
            _emp, gate = auth.authorize(conn, tok_a)
            self.assertEqual(gate, "app")
            self.assertFalse(auth.me(conn, tok_b)["is_admin"])
            self.assertTrue(auth.me(conn, tok_a)["is_admin"])
            accounts = {a["email"] for a in auth.list_accounts(conn)}
            self.assertEqual(accounts, {"ada@foap.test", "bo@foap.test"})
        finally:
            conn.close()


class HttpHelpers:
    def _serve(self, db_path):
        import server as srv
        srv.Handler.db_path = db_path
        httpd = HTTPServer(("127.0.0.1", 0), srv.Handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd, thread, port

    def _open(self, db):
        conn = sqlite3.connect(db)
        schema.init_db(conn)
        conn.close()

    def _req(self, base, path, data=None, cookie=""):
        req = urllib.request.Request(
            base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET")
        if cookie:
            req.add_header("Cookie", cookie)
        return req

    def _call(self, base, path, data=None, cookie=""):
        try:
            with urllib.request.urlopen(
                    self._req(base, path, data, cookie)) as resp:
                return resp.status, dict(resp.headers), \
                    json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), \
                json.loads(exc.read() or b"{}")

    def _cookie(self, headers):
        for key, value in headers.items():
            if key.lower() == "set-cookie" and value.startswith(
                    "ci_session="):
                return value.split(";", 1)[0]
        return ""


class LastAdminTest(AuthCase, HttpHelpers):
    def _two_admins(self, conn):
        a = auth.admin_create(conn, "root", "a@foap.test", role="admin")
        b = auth.admin_create(conn, "root", "b@foap.test", role="admin")
        return a, b

    def test_sole_admin_cannot_be_suspended_revoked_demoted(self):
        conn = _conn()
        try:
            solo = auth.admin_create(conn, "root", "solo@foap.test",
                                     role="admin")
            for op in (lambda: auth.admin_set_status(
                    conn, "root", solo["id"], "suspended",
                    "EMPLOYEE_SUSPENDED"),
                       lambda: auth.admin_set_status(
                    conn, "root", solo["id"], "revoked",
                    "EMPLOYEE_REVOKED"),
                       lambda: auth.admin_set_role(
                    conn, "root", solo["id"], "employee")):
                with self.assertRaises(auth.AuthError):
                    op()
            emp = auth.get_employee(conn, solo["id"])
            self.assertEqual((emp["role"], emp["status"]),
                             ("admin", "active"))
            # Refusals leave no audit trail behind.
            self.assertEqual(
                [e["action"] for e in auth.admin_audit_list(conn)],
                ["EMPLOYEE_CREATED"])
        finally:
            conn.close()

    def test_second_admin_makes_ops_legal(self):
        conn = _conn()
        try:
            a, b = self._two_admins(conn)
            auth.admin_set_role(conn, a["id"], b["id"], "employee")
            self.assertEqual(
                auth.get_employee(conn, b["id"])["role"], "employee")
            auth.admin_set_status(conn, a["id"], b["id"], "suspended",
                                  "EMPLOYEE_SUSPENDED")
            auth.admin_set_status(conn, a["id"], b["id"], "active",
                                  "EMPLOYEE_REACTIVATED")
            # Now A is the last active admin again: suspending A fails.
            with self.assertRaises(auth.AuthError):
                auth.admin_set_status(conn, a["id"], a["id"], "suspended",
                                      "EMPLOYEE_SUSPENDED")
        finally:
            conn.close()

    def test_last_admin_rule_over_http(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            boss = auth.admin_create(conn, "root", "boss@foap.test",
                                     role="admin")
            token, _e, _c = self._oauth_login(conn, {
                "workos_user_id": "w-boss", "email": "boss@foap.test",
                "first_name": "B", "last_name": "", "avatar_url": "",
                "verified": True, "provider": "google"})
            conn.close()
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                admin = "ci_session=" + token
                code, _h, body = self._call(
                    base, "/api/admin/employees/%s/revoke" % boss["id"],
                    {}, cookie=admin)
                self.assertEqual(code, 409)
                self.assertIn("admin", body["error"].lower())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)



class HttpAuthTest(AuthCase, HttpHelpers):
    def test_fresh_db_denies_anonymous(self):
        # Zero employees: every data API still requires login.
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            self._open(db)
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                for path in ("/api/campaigns", "/api/benchmarks",
                             "/api/admin/employees"):
                    code, _h, body = self._call(base, path)
                    self.assertIn(code, (401, 403))
                    self.assertIn(body.get("gate"), ("login", "pending",
                                                     "forbidden"))
                code, _h, body = self._call(base, "/api/health")
                self.assertEqual(code, 200)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)

    def test_bootstrap_from_zero_employees(self):
        # Fresh DB + configured admin email: first OAuth login mints
        # the first (admin) employee; anyone else stays pending.
        os.environ["CREATIVE_INTEL_ADMIN_EMAIL"] = "founder@foap.test"
        conn = _conn()
        try:
            token, emp, created = self._oauth_login(conn, {
                "workos_user_id": "w-root", "email": "founder@foap.test",
                "first_name": "F", "last_name": "", "avatar_url": "",
                "verified": True, "provider": "google"})
            self.assertTrue(created)
            self.assertEqual((emp["role"], emp["status"]),
                             ("admin", "active"))
            _emp, gate = auth.authorize(conn, token)
            self.assertEqual(gate, "app")
        finally:
            conn.close()

    def test_pending_cannot_touch_data(self):
        # Goal items 9 + 18 (frontend flags can't bypass the backend).
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            self._stub_exchange(ID_A)
            started = auth.start_oauth(conn, "google")
            ident = auth.finish_oauth(conn, "auth_code", started["state"])
            token, _emp, _c = auth.login_identity(conn, ident)
            conn.close()
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                jar = "ci_session=" + token
                code, _h, body = self._call(base, "/api/campaigns",
                                            cookie=jar)
                self.assertEqual(code, 403)
                self.assertEqual(body["gate"], "pending")
                code, _h, _b = self._call(
                    base, "/api/ingest",
                    {"platform": "meta", "csv": "a\n"}, cookie=jar)
                self.assertEqual(code, 403)
                code, _h, _b = self._call(
                    base, "/api/admin/employees", cookie=jar)
                self.assertIn(code, (401, 403, 404))
                code, _h, _b = self._call(base, "/api/campaigns")
                self.assertEqual(code, 401)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)

    def test_admin_journey_over_http(self):
        # Goal items 10-11, 15-17.
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            boss = auth.admin_create(conn, "root", "boss@foap.test",
                                     role="admin")
            token_b, _e, _c = self._oauth_login(conn, {
                "workos_user_id": "w-boss", "email": "boss@foap.test",
                "first_name": "B", "last_name": "", "avatar_url": "",
                "verified": True, "provider": "google"})
            self.assertEqual(_e["id"], boss["id"])
            conn.close()
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                admin = "ci_session=" + token_b
                code, _h, body = self._call(
                    base, "/api/admin/employees", cookie=admin)
                self.assertEqual(code, 200)
                self.assertTrue(any(
                    e["email"] == "boss@foap.test"
                    for e in body["employees"]))
                # Newcomer signs in first: pending request, no app access.
                conn3 = sqlite3.connect(db)
                self._stub_exchange({
                    "workos_user_id": "w-new", "email": "new@foap.test",
                    "first_name": "New", "last_name": "Hire",
                    "avatar_url": "", "verified": True,
                    "provider": "google"})
                st3 = auth.start_oauth(conn3, "google")
                ident3 = auth.finish_oauth(conn3, "auth_code",
                                           st3["state"])
                _tok3, emp3, created3 = auth.login_identity(conn3, ident3)
                conn3.close()
                self.assertTrue(created3)
                self.assertEqual(emp3["status"], "pending")
                new_id = emp3["id"]
                code, _h, body = self._call(
                    base, "/api/admin/employees", cookie=admin)
                self.assertTrue(any(
                    e["status"] == "pending" for e in body["employees"]))
                code, _h, _b = self._call(
                    base, "/api/admin/employees/%s/approve" % new_id, {},
                    cookie=admin)
                self.assertEqual(code, 200)
                code, _h, body = self._call(
                    base, "/api/admin/audit?limit=10", cookie=admin)
                self.assertTrue(any(
                    e["action"] == "EMPLOYEE_APPROVED"
                    for e in body["events"]))
                # Non-admin employee cannot touch admin APIs.
                conn2 = sqlite3.connect(db)
                self._stub_exchange(ID_A)
                st = auth.start_oauth(conn2, "google")
                ident = auth.finish_oauth(conn2, "auth_code", st["state"])
                token_a, _ea, _ca = auth.login_identity(conn2, ident)
                conn2.close()
                empjar = "ci_session=" + token_a
                code, _h, _b = self._call(
                    base, "/api/admin/employees", cookie=empjar)
                self.assertEqual(code, 403)
                code, _h, _b = self._call(
                    base, "/api/admin/employees/%s/suspend" % new_id, {},
                    cookie=empjar)
                self.assertEqual(code, 403)
                # ...but the admin's approval lets the newcomer in.
                code, _h, body = self._call(base, "/api/auth/me",
                                            cookie=admin)
                self.assertTrue(body["is_admin"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)

    def test_logout_and_switch_over_http(self):
        # Goal items 19-20, 22-23.
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            token_a, emp_a, _c = self._oauth_login(conn, ID_A)
            token_b, emp_b, _c2 = self._oauth_login(conn, ID_B)
            auth.admin_set_status(conn, "root", emp_a["id"], "active",
                                  "EMPLOYEE_APPROVED")
            conn.close()
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                jar_a = "ci_session=" + token_a
                code, _h, body = self._call(base, "/api/auth/me",
                                            cookie=jar_a)
                self.assertEqual(body["gate"], "app")
                code, _h, body = self._call(
                    base, "/api/auth/switch", {"employee_id": emp_b["id"]},
                    cookie=jar_a)
                self.assertEqual(code, 200)
                # Old account untouched; new cookie is pending-scoped.
                code, _h, body = self._call(base, "/api/auth/me",
                                            cookie=jar_a)
                self.assertEqual(body["gate"], "app")
                code, _h, _b = self._call(base, "/api/auth/logout",
                                          {}, cookie=jar_a)
                self.assertEqual(code, 200)
                code, _h, _b = self._call(base, "/api/auth/me",
                                          cookie=jar_a)
                self.assertEqual(code, 200)
                self.assertEqual(_b["gate"], "login")
                jar_b = "ci_session=" + token_b
                code, _h, body = self._call(base, "/api/auth/me",
                                            cookie=jar_b)
                self.assertEqual(body["gate"], "pending")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)

    def test_secrets_never_leak(self):
        # Goal item 29: force WorkOS + validation failures, scan output.
        os.environ["CREATIVE_INTEL_KEY_WORKOS"] = "sk-live-SECRET-XYZ"
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        stub = None
        thread2 = None
        try:
            self._open(db)
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port

                class Stub(BaseHTTPRequestHandler):
                    def do_POST(self):
                        length = int(self.headers.get("Content-Length", 0))
                        self.rfile.read(length)
                        body = json.dumps({"message": "bad stuff",
                                           "code": "bad"}).encode()
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                    def log_message(self, *a):
                        pass

                stub = HTTPServer(("127.0.0.1", 0), Stub)
                sport = stub.server_address[1]
                thread2 = threading.Thread(target=stub.serve_forever,
                                           daemon=True)
                thread2.start()
                os.environ["CREATIVE_INTEL_BASE_WORKOS"] = \
                    "http://127.0.0.1:%d" % sport
                code, _h, _b = self._call(
                    base, "/api/auth/oauth/start", {"provider": "google"})
                self.assertEqual(code, 200)
                code, _h, body = self._call(
                    base, "/api/auth/oauth/finish",
                    {"code": "x", "state": "made-up"})
                self.assertEqual(code, 409)
                blob = json.dumps(body)
                self.assertNotIn("SECRET-XYZ", blob)
                self.assertNotIn("sk-live", blob)
                code, _h, body = self._call(
                    base, "/api/auth/oauth/start", {"provider": "nope"})
                self.assertEqual(code, 409)
                self.assertNotIn("SECRET-XYZ", json.dumps(body))
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            if stub is not None:
                stub.shutdown()
            if thread2 is not None:
                thread2.join(timeout=10)
            os.unlink(db)

    def test_callback_lands_without_token_in_url(self):
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            self._stub_exchange(ID_A)
            started = auth.start_oauth(conn, "google")
            conn.close()
            httpd, thread, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                req = urllib.request.Request(
                    base + "/api/auth/callback?code=auth_code&state="
                    + started["state"])
                opener = urllib.request.build_opener(NoRedirect())
                try:
                    opener.open(req)
                    self.fail("expected redirect")
                except Redirected as red:
                    self.assertEqual(red.code, 302)
                    self.assertTrue(red.url == "/" or
                                    red.url.endswith("/"))
                    self.assertNotIn("ci_session=", red.url)
                    cookie = self._cookie(red.headers)
                    self.assertTrue(cookie.startswith("ci_session="))
                    code, _h, body = self._call(base, "/api/auth/me",
                                                cookie=cookie)
                    self.assertEqual(body["gate"], "pending")
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)


class Redirected(Exception):
    def __init__(self, code, url, headers):
        super().__init__("redirect")
        self.code = code
        self.url = url
        self.headers = headers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Redirected(code, newurl, headers)


class FrontendGateTest(unittest.TestCase):
    def test_login_screen_present_and_clean(self):
        # Goal items 1 (static-HTML half of the E2E substitution).
        html = open(os.path.join(
            os.path.dirname(__file__), "..", "Web", "Index.html"),
            encoding="utf-8").read()
        self.assertIn("Welcome to Creative Intelligence", html)
        for label in ("Continue with Google", "Continue with Microsoft",
                      "Continue with Apple", "Continue with GitHub"):
            self.assertIn(label, html)
        self.assertIn("Access pending", html)
        self.assertIn("Admin — Employees", html)
        self.assertNotIn("CREATIVE_INTEL_KEY_WORKOS", html)
        self.assertNotIn("sk-live", html)
        self.assertNotIn("sk_test", html)
        self.assertNotIn("localStorage", html)

    def test_no_licensing_concepts(self):
        # Goal item 10 of the final audit + section 29.
        root = os.path.join(os.path.dirname(__file__), "..")
        hits = []
        for dirpath, _dirs, files in os.walk(root):
            if "__pycache__" in dirpath:
                continue
            for name in files:
                if not name.endswith((".py", ".html")):
                    continue
                if name == "test_auth.py":
                    continue  # this file names the banned concepts
                path = os.path.join(dirpath, name)
                text = open(path, encoding="utf-8", errors="replace").read()
                for bad in ("dodo", "needs_license", "licence_",
                            "license_key", "grace_period", "device_limit"):
                    if bad in text.lower():
                        hits.append("%s: %s" % (path, bad))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()

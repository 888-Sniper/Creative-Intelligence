"""Shared login helper for live-server tests (stdlib unittest).

Production authentication is default-deny from the very first launch:
every protected API needs a session cookie for an active employee.
This helper mints an active employee plus session directly against a
test database file so live-server tests can act as signed-in staff::

    from auth_help import authed
    cookie = authed(db_path)                      # active admin session
    req = urllib.request.Request(url, headers={"Cookie": cookie})
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import auth, schema


def authed(db_path, email="staff@example.com", role="admin"):
    """Return a Cookie header value for an active employee session."""
    conn = sqlite3.connect(db_path)
    try:
        schema.init_db(conn)
        try:
            emp = auth.admin_create(conn, "test-helper", email, role=role)
        except auth.AuthError:
            emp = auth.find_employee(conn, "", email.strip().lower())
        token = auth.create_session(conn, emp["id"],
                                    emp.get("workos_user_id") or "")
    finally:
        conn.close()
    return "%s=%s" % (auth.COOKIE_NAME, token)


def req(url, cookie, data=None, content_type="application/json"):
    """Build a GET/POST request carrying the session cookie."""
    import urllib.request
    headers = {"Cookie": cookie}
    if data is not None:
        headers["Content-Type"] = content_type
    return urllib.request.Request(url, data=data, headers=headers)

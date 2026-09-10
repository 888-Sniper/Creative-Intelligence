"""Session minting for tests that drive a real server subprocess.

The FastAPI TestClient tests use tests/conftest.py instead; this helper
exists for the launch-path tests whose server runs in another process,
so the cookie is minted straight into the database file.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store
from conftest import employee_session


def authed(db_path, email="staff@example.com", role="admin"):
    """Return a Cookie header value for an active employee session."""
    with employee_session(db_path) as sess:
        try:
            employee = emp_store.admin_create(sess, "test-helper", email,
                                              role=role)
        except emp_store.StoreError:
            employee = emp_store.find_employee(sess, "", email.strip().lower())
        token = emp_store.create_session(sess, employee.id,
                                         employee.workos_user_id or "")
    return "ci_session=%s" % token


def req(url, cookie, data=None, content_type="application/json"):
    """Build a GET/POST request carrying the session cookie."""
    import urllib.request
    headers = {"Cookie": cookie}
    if data is not None:
        headers["Content-Type"] = content_type
    return urllib.request.Request(url, data=data, headers=headers)

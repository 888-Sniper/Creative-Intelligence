"""Request-schema tests (pytest + TestClient).

Every external write API validates shape at the HTTP boundary: enum
membership, maximum lengths, list limits, ISO dates and allowed
filter/KPI values. Malformed bodies fail with the 409 contract —
never a 500 from library code.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import employee_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_owner(tmp_path):
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    app = create_app(db, settings)
    with employee_session(db) as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        cookie = "ci_session=" + emp_store.create_session(
            sess, boss.id, "")
    http = TestClient(app, raise_server_exceptions=False)
    http.headers.update({"Cookie": cookie})
    return http


def test_ask_rejects_missing_and_oversize_question(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/ask", json={}).status_code == 409
    assert http.post("/api/ask",
                     json={"question": "x" * 2001}).status_code == 409
    assert http.post("/api/ask",
                     json={"question": "ok",
                           "filters": {"nope": ["x"]}}).status_code == 409
    assert http.post("/api/ask",
                     json={"question": "ok",
                           "filters": {"date_from": ["yesterday"]}}
                     ).status_code == 409


def test_ask_accepts_scoped_question(tmp_path):
    http = make_owner(tmp_path)
    resp = http.post("/api/ask",
                     json={"question": "how are we doing?",
                           "filters": {"platform": ["meta"],
                                       "date_from": ["2026-01-01"]}})
    assert resp.status_code == 200, resp.text


def test_reviews_mark_needs_integer_id(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/reviews/mark", json={}).status_code == 409
    assert http.post("/api/reviews/mark",
                     json={"review_id": "abc"}).status_code == 409


def test_export_needs_bounded_keys(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/export", json={}).status_code == 409
    assert http.post("/api/export",
                     json={"creative_keys": ["k%d" % i for i in range(51)]}
                     ).status_code == 409


def test_cohort_validates_name_and_filters(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/cohorts", json={}).status_code == 409
    assert http.post("/api/cohorts",
                     json={"name": "c",
                           "filters": {"bogus": ["x"]}}).status_code == 409
    resp = http.post("/api/cohorts",
                     json={"name": "c1",
                           "filters": {"platform": ["meta"]}})
    assert resp.status_code == 200, resp.text


def test_compare_post_validates_rank_by(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/compare/campaigns",
                     json={"rank_by": "vibes"}).status_code == 409
    # Empty data fails downstream (no campaigns), but must pass
    # schema validation first — i.e. not an "Invalid ..." rejection.
    resp = http.post("/api/compare/campaigns",
                     json={"campaigns": [], "rank_by": "roas"})
    assert resp.status_code == 409
    assert "Invalid campaign comparison" not in resp.json()["error"]


def test_report_validates_format_and_kpis(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/report",
                     json={"format": "exe"}).status_code == 409
    assert http.post("/api/report",
                     json={"kpis": ["cpa", "vibes"]}).status_code == 409
    assert http.post("/api/report",
                     json={"benchmark_scope": "everywhere"}
                     ).status_code == 409


def test_annotate_needs_object(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/creatives/k1/annotate",
                     json={}).status_code == 409
    assert http.post("/api/creatives/k1/annotate",
                     json={"annotation": ["not", "an", "object"]}
                     ).status_code == 409


def test_dispatch_validates_per_route(tmp_path):
    http = make_owner(tmp_path)
    assert http.post("/api/retention", json={}).status_code == 409
    assert http.post("/api/retention",
                     json={"creative_key": "k",
                           "points": [["a", "b"]]}).status_code == 409
    assert http.post("/api/views/delete",
                     json={"id": "x"}).status_code == 409
    assert http.post("/api/ingest", json={}).status_code == 409
    assert http.post("/api/ingest",
                     json={"platform": "meta"}).status_code == 409
    assert http.post("/api/sync/run", json={}).status_code == 409
    assert http.post("/api/views",
                     json={"name": "", "state": {}}).status_code == 409
    resp = http.post("/api/views/delete", json={"id": 424242})
    assert resp.status_code == 409  # unknown view, not a crash

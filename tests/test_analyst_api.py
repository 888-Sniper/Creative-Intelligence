"""Foap Analyst API + worker wiring tests (spec sections 14, 18, 20).

Drives the real FastAPI app with authorized employee sessions:
ingest seeding, analyst turns through the durable job path,
conversation listing/detail, finding accept/reject with
cross-owner isolation, and auth gates.
"""

import contextlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))
sys.path.insert(0, os.path.dirname(__file__))

from ci_backend import employees as emp_store
from ci_backend.app import create_app
from ci_backend.config import Settings
from conftest import employee_session

CSV = ("Campaign,Ad,Impressions,2s views,3s views,25% views,50% views,"
       "Completions,Watch time,Video views,Spend,Link clicks,Message\n"
       "C,A,5000,1500,1200,900,500,300,5900,5000,50,40,promotional\n"
       "C,B,5000,500,400,300,150,80,5100,5000,50,10,neutral\n"
       "C,C,5000,200,150,120,60,30,3000,5000,50,5,neutral\n")


def make_client(root, **settings_kw):
    db = str(root / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]", **settings_kw)
    app = create_app(db, settings)
    return TestClient(app, raise_server_exceptions=False), db


@contextlib.contextmanager
def tmp_root():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


class AnalystApiTest(unittest.TestCase):
    def _owner(self, root, email="boss@foap.test", **headers):
        http, db = make_client(root, admin_email=email)
        with employee_session(db) as sess:
            boss = emp_store.admin_create(sess, "root", email,
                                          role="admin")
            cookie = ("ci_session="
                      + emp_store.create_session(sess, boss.id, ""))
        authed = TestClient(http.app, raise_server_exceptions=False)
        authed.headers.update({"Cookie": cookie, **headers})
        return authed

    def _seed(self, http):
        r = http.post("/api/ingest",
                      json={"platform": "tiktok", "csv": CSV})
        self.assertEqual(r.status_code, 200, r.text)

    def test_unauthenticated_refused(self):
        with tmp_root() as root:
            http, _db = make_client(root)
            r = http.post("/api/analyst/ask",
                          json={"question": "hi"})
            self.assertIn(r.status_code, (401, 403))

    def test_full_turn_and_history(self):
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            r = http.post("/api/analyst/ask", json={
                "question": "Wylicz 2s hook rate dla każdej kreacji.",
                "scope": {"campaign": ["C"]}})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual(body["task"], "full_analysis")
            self.assertIn("30,0%", body["text"])
            conv_id = body["conversation_id"]

            r = http.get("/api/analyst/conversations")
            self.assertEqual(r.status_code, 200)
            ids = [c["id"] for c in r.json()["conversations"]]
            self.assertIn(conv_id, ids)

            r = http.get("/api/analyst/conversations/%s" % conv_id)
            self.assertEqual(r.status_code, 200)
            detail = r.json()
            self.assertEqual(len(detail["messages"]), 2)
            self.assertEqual(detail["messages"][0]["role"], "user")

    def test_condense_turn(self):
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            r = http.post("/api/analyst/ask", json={
                "question": "Wylicz 2s hook rate dla każdej kreacji.",
                "scope": {"campaign": ["C"]}})
            conv_id = r.json()["conversation_id"]
            r = http.post("/api/analyst/ask", json={
                "conversation_id": conv_id,
                "question": "Napisz rekomendacje do kolejnej kampanii.",
                "scope": {"campaign": ["C"]}})
            self.assertEqual(r.json()["task"], "recommendations")
            r = http.post("/api/analyst/ask", json={
                "conversation_id": conv_id,
                "question": "Ogranicz się do 3 punktów.",
                "scope": {"campaign": ["C"]}})
            body = r.json()
            self.assertEqual(body["task"], "condense")
            self.assertEqual(body["payload"]["condensed_to"], 3)

    def test_max_points_caps_rendering(self):
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            r = http.post("/api/analyst/ask", json={
                "question": "Napisz rekomendacje do kolejnej kampanii.",
                "scope": {"campaign": ["C"]},
                "max_points": 1})
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual(body["task"], "recommendations")
            self.assertEqual(len(body["payload"]["recommendations"]), 1)
            self.assertEqual(body["payload"]["condensed_to"], 1)
            r = http.post("/api/analyst/ask", json={
                "question": "Napisz rekomendacje do kolejnej kampanii.",
                "scope": {"campaign": ["C"]},
                "max_points": 99})
            self.assertEqual(r.status_code, 409)

    def test_finding_status_and_isolation(self):
        with tmp_root() as root:
            http = self._owner(root, email="boss@foap.test")
            self._seed(http)
            r = http.post("/api/analyst/ask", json={
                "question": "Wylicz 2s hook rate dla każdej kreacji.",
                "scope": {"campaign": ["C"]}})
            conv_id = r.json()["conversation_id"]
            db = str(root / "app.db")
            conn = sqlite3.connect(db)
            try:
                row = conn.execute(
                    "SELECT id FROM analyst_findings LIMIT 1").fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            r = http.post("/api/analyst/findings/%s" % row[0],
                          json={"status": "accepted"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["status"], "accepted")
            # Another employee can neither relabel it nor open chat.
            other = self._owner(root, email="other@foap.test")
            r = other.post("/api/analyst/findings/%s" % row[0],
                           json={"status": "rejected"})
            self.assertEqual(r.status_code, 409, r.text)
            r = other.get("/api/analyst/conversations/%s" % conv_id)
            self.assertEqual(r.status_code, 404)

    def test_validation_rejects_bad_objective(self):
        with tmp_root() as root:
            http = self._owner(root)
            r = http.post("/api/analyst/ask", json={
                "question": "hi", "objective": "virality"})
            self.assertEqual(r.status_code, 409)

    def test_workbook_download(self):
        with tmp_root() as root:
            http = self._owner(root)
            r = http.get("/api/analyst/workbook")
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("spreadsheetml.sheet", r.headers["content-type"])
            self.assertIn("foap-analyst-workbook.xlsx",
                          r.headers["content-disposition"])
            self.assertTrue(r.content.startswith(b"PK"))

    def test_report_one_pager_and_xlsx(self):
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            payload = {"scope": {"campaign": ["C"]}, "objective": "reach",
                       "language": "pl",
                       "sections": ["results", "best_worst",
                                    "recommendations", "tests",
                                    "methodology"]}
            r = http.post("/api/analyst/report", json=payload)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual(body["format"], "one-pager")
            self.assertIn("Raport Foap Analyst", body["markdown"])
            self.assertIn("Rekomendacje (maks. 3)", body["markdown"])
            self.assertEqual(body["meta"]["language"], "pl")
            self.assertEqual(body["meta"]["sections"],
                             payload["sections"])
            payload["fmt"] = "xlsx"
            r = http.post("/api/analyst/report", json=payload)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertIn("spreadsheetml.sheet",
                          r.headers["content-type"])
            self.assertTrue(r.content.startswith(b"PK"))

    def test_report_rejects_unknown_section(self):
        with tmp_root() as root:
            http = self._owner(root)
            r = http.post("/api/analyst/report",
                          json={"sections": ["vibes"]})
            self.assertEqual(r.status_code, 409)

    def test_creatives_cards(self):
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            r = http.get("/api/analyst/creatives?campaign=C")
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertEqual(len(body["creatives"]), 3)
            card = body["creatives"][0]
            self.assertEqual(
                [layer["layer"] for layer in card["layers"]],
                ["stop", "hold", "depth", "brand", "efficiency"])
            self.assertIn("hook_rate_2s_impr", card["metrics"])
            self.assertTrue(card["finding"]["primary_signal"])
            self.assertEqual(body["objective"], "reach")
            r = http.get("/api/analyst/creatives?objective=virality")
            self.assertEqual(r.status_code, 409)

    def test_finding_instances_are_scoped_and_sticky(self):
        # A06: same rule on two creatives -> two rows; accept survives
        # re-analysis; other conversations get their own rows.
        with tmp_root() as root:
            http = self._owner(root)
            self._seed(http)
            ask = {"question": "Which creative is best?",
                   "scope": {"campaign": ["C"]}}
            first = http.post("/api/analyst/ask", json=ask).json()
            conv = first["conversation_id"]
            db = str(root / "app.db")

            def _rows():
                conn = sqlite3.connect(db)
                try:
                    return conn.execute(
                        "SELECT id, conversation_id, status"
                        " FROM analyst_findings").fetchall()
                finally:
                    conn.close()
            rows = _rows()
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(len({r[0] for r in rows}), len(rows))
            self.assertTrue(all(r[1] == conv for r in rows))
            target = rows[0][0]
            r = http.post("/api/analyst/findings/%s" % target,
                          json={"status": "accepted"})
            self.assertEqual(r.status_code, 200, r.text)
            # Re-ask the same question: evidence refreshes, the
            # decision sticks, no duplicate rows appear.
            http.post("/api/analyst/ask",
                      json=dict(ask, conversation_id=conv))
            rows = _rows()
            kept = [r for r in rows if r[0] == target]
            self.assertEqual(len(rows), len({r[0] for r in rows}))
            self.assertEqual(kept[0][2], "accepted")
            # A second conversation owns separate instances.
            second = http.post("/api/analyst/ask", json=ask).json()
            rows = _rows()
            other = [r for r in rows if r[1] == second["conversation_id"]]
            self.assertTrue(other)
            self.assertFalse({r[0] for r in other}
                             & {target})

    def test_report_unauthenticated_refused(self):
        with tmp_root() as root:
            http, _db = make_client(root)
            r = http.post("/api/analyst/report", json={})
            self.assertIn(r.status_code, (401, 403))
            r = http.get("/api/analyst/workbook")
            self.assertIn(r.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()

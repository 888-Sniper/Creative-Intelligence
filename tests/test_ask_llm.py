"""LLM Ask Data tests: grounded fact pack, live branch, fallbacks.

The rule engine stays the default; the LLM path only engages when an
ask_facts-capable llm is passed, answers strictly over the computed
fact pack, keeps review-to-zero rows, and falls back to rules on any
live failure.
"""

import json
import os
import sqlite3
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import ingest, providers, qa, schema

CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
       "Link Clicks,Conversions,Platform\n"
       "A,a1,k1,100,10000,200,10,meta\n"
       "B,b1,k2,300,30000,300,15,tiktok\n")


def fresh():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta"))
    return conn


class FakeLlm:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error
        self.seen = None

    def ask_facts(self, question, facts):
        self.seen = (question, facts)
        if self.error:
            raise self.error
        return self.text


GOOD = json.dumps({"answer": "Campaign B leads on spend at $300.",
                   "used": ["campaigns", "totals"]})


class AskLlmTest(unittest.TestCase):
    def test_ask_prompt_covers_all_fact_sections(self):
        missing = [key for key in qa._USED_SOURCES
                   if '"%s"' % key not in providers.LiveLlm.ASK_PROMPT]
        self.assertEqual(missing, [])

    def test_llm_answer_uses_fact_pack(self):
        conn = fresh()
        try:
            fake = FakeLlm(GOOD)
            got = qa.answer(conn, "which campaign leads?", llm=fake)
            self.assertIn("Campaign B leads", got["answer"])
            self.assertIn("[LLM]", got["answer"])
            self.assertIn("Uploaded CSV", got["sources"])
            self.assertIsNotNone(got["review_id"])
            _q, facts = fake.seen
            self.assertEqual(facts["totals"]["spend"], 400.0)
            self.assertEqual(len(facts["campaigns"]), 2)
            self.assertEqual(qa.pending_count(conn), 1)
        finally:
            conn.close()

    def test_garbage_falls_back_to_rules(self):
        conn = fresh()
        try:
            got = qa.answer(conn, "what is spend?",
                            llm=FakeLlm("definitely not json"))
            self.assertNotIn("[LLM]", got["answer"])
            self.assertIn("Total spend", got["answer"])
            self.assertIsNotNone(got["review_id"])
        finally:
            conn.close()

    def test_live_error_falls_back_to_rules(self):
        conn = fresh()
        try:
            got = qa.answer(
                conn, "what is spend?",
                llm=FakeLlm(error=providers.ProviderUnavailable("down")))
            self.assertNotIn("[LLM]", got["answer"])
            self.assertIn("Total spend", got["answer"])
        finally:
            conn.close()

    def test_no_llm_uses_rules(self):
        conn = fresh()
        try:
            got = qa.answer(conn, "what is spend?")
            self.assertNotIn("[LLM]", got["answer"])
            self.assertIn("Total spend", got["answer"])
        finally:
            conn.close()

    def test_mock_llm_without_ask_facts_falls_back(self):
        conn = fresh()
        try:
            got = qa.answer(conn, "what is spend?",
                            llm=providers.MockLlm())
            self.assertNotIn("[LLM]", got["answer"])
        finally:
            conn.close()

    def test_no_data_no_llm_call(self):
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            fake = FakeLlm(GOOD)
            got = qa.answer(conn, "anything?", llm=fake)
            self.assertIsNone(fake.seen)
            self.assertIn("No uploaded data", got["answer"])
        finally:
            conn.close()


class AskHttpTest(unittest.TestCase):
    """Real HTTP ask path: LiveLlm.ask_facts against a stub chat server."""

    @classmethod
    def setUpClass(cls):
        class Stub(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                body = json.dumps({"choices": [{"message": {
                    "content": GOOD}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        cls._srv = HTTPServer(("127.0.0.1", 0), Stub)
        cls.base = "http://127.0.0.1:%d" % cls._srv.server_address[1]
        cls._thread = threading.Thread(target=cls._srv.serve_forever,
                                       daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._srv.shutdown()
        cls._thread.join(timeout=10)
        cls._srv.server_close()

    def test_live_ask_end_to_end(self):
        saved = dict(os.environ)
        os.environ["CREATIVE_INTEL_PROVIDER_MODE"] = "live"
        os.environ["CREATIVE_INTEL_KEY_DEEPSEEK"] = "dummy"
        os.environ["CREATIVE_INTEL_BASE_DEEPSEEK"] = self.base
        try:
            llm = providers.LiveLlm([("deepseek", "deepseek-v4-flash",
                                      "active")])
            conn = fresh()
            try:
                got = qa.answer(conn, "which campaign leads?", llm=llm)
                self.assertIn("[LLM]", got["answer"])
                self.assertIn("Campaign B leads", got["answer"])
            finally:
                conn.close()
        finally:
            os.environ.clear()
            os.environ.update(saved)


class AskAnswerLevelTest(unittest.TestCase):
    """Best-X answers rank at the requested level and share tied leads."""

    def _conn(self, meta_rev, tik_rev):
        return self._conn_rows([
            ("meta", "A", "k1", 100, meta_rev, 1),
            ("tiktok", "B", "k2", 100, tik_rev, 1)])

    def _conn_rows(self, rows):
        conn = sqlite3.connect(":memory:")
        schema.init_db(conn)
        conn.executemany(
            "INSERT INTO ads (platform, campaign, ad_name, creative_key,"
            " spend, impressions, clicks, conversions, revenue,"
            " revenue_reported, date)"
            " VALUES (?,?,?,?,?,10000,200,10,?,?,?)",
            [(platform, campaign, key, key, spend, revenue, reported,
              "2026-08-01")
             for platform, campaign, key, spend, revenue, reported
             in rows])
        return conn

    def test_platform_question_ranks_platforms(self):
        conn = self._conn(200, 300)
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("Top platform by ROAS is TikTok at 3.0x",
                          got["answer"])
            self.assertNotIn("Top creative", got["answer"])
        finally:
            conn.close()

    def test_platform_tie_is_declared(self):
        conn = self._conn(200, 200)
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("tied", got["answer"])
            self.assertIn("Meta", got["answer"])
            self.assertIn("TikTok", got["answer"])
        finally:
            conn.close()

    def test_sub_display_precision_gap_is_still_a_tie(self):
        # ROAS prints at one decimal: 2.0x vs 2.0x (raw 2.004x)
        # must tie rather than crown the unrounded leader, matching
        # the takeaways the UI prints beside the winner sentence.
        conn = self._conn(200, 200.4)
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("tied", got["answer"])
            self.assertIn("2.0x", got["answer"])
        finally:
            conn.close()

    def test_campaign_question_ranks_campaigns(self):
        conn = self._conn(200, 300)
        try:
            got = qa.answer(conn, "Which campaign has the best ROAS?")
            self.assertIn("Top campaign by ROAS is B at 3.0x",
                          got["answer"])
        finally:
            conn.close()

    def test_roas_uses_only_revenue_reporting_spend(self):
        # Meta matched ROAS is 200/100 = 2.0; its extra unreported
        # spend must not dilute it to 1.0 behind TikTok's 1.5.
        conn = self._conn_rows([
            ("meta", "A", "k1", 100, 200, 1),
            ("meta", "A", "k2", 100, 0, 0),
            ("tiktok", "B", "k3", 100, 150, 1)])
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("Top platform by ROAS is Meta at 2.0x",
                          got["answer"])
        finally:
            conn.close()

    def test_roas_without_reported_revenue_has_no_winner(self):
        conn = self._conn_rows([
            ("meta", "A", "k1", 100, 200, 0),
            ("tiktok", "B", "k2", 100, 300, 0)])
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("no ROAS winner", got["answer"])
            self.assertNotIn("Top platform by ROAS is", got["answer"])
        finally:
            conn.close()

    def test_roas_reported_zero_stays_measurable(self):
        conn = self._conn_rows([
            ("meta", "A", "k1", 100, 0, 1),
            ("tiktok", "B", "k2", 100, 300, 0)])
        try:
            got = qa.answer(conn, "Which platform has the best ROAS?")
            self.assertIn("Top platform by ROAS is Meta at 0.0x",
                          got["answer"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()

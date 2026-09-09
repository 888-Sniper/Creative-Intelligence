"""Provider-pattern + grounded-QA tests (stdlib unittest).

Covers the Nextly-ported provider pattern (Active/Fallback race, daily
models sync, Keychain configured/missing, mock default, cue caps,
thinking handling) and grounded Q&A with the review-to-zero export gate.
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import export_gate, ingest, providers, qa, schema  # noqa: E402

META_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions\n"
            "C1,A1,hook-a,100,10000,200,10\n"
            "C1,A2,hook-b,300,30000,300,15\n")


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def seeded_db():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
    return conn


class ProviderPatternTest(unittest.TestCase):
    def test_mock_default(self):
        self.assertEqual(providers.mode(), "mock")
        matrix = providers.provider_matrix()
        self.assertGreater(len(matrix), 0)
        self.assertTrue(all(m["status"] == "mock" for m in matrix
                            if m["provider"] != "ollama"))

    def test_registry_covers_all_families(self):
        names = set(providers.REGISTRY)
        for expected in ("deepgram", "groq-whisper", "gemini",
                         "muse-glimmer", "gpt", "claude", "glm-5v",
                         "deepseek", "kimi", "grok", "teamorouter",
                         "openrouter", "ollama", "litellm"):
            self.assertIn(expected, names)

    def test_race_prefers_active_falls_back(self):
        winner, value = providers.race(
            ["a"], ["b"], lambda item: "ok-" + item if item == "b" else "")
        self.assertEqual((winner, value), ("b", "ok-b"))
        winner, value = providers.race(
            ["a1", "a2"], ["b"], lambda item: "ok-" + item)
        self.assertEqual(value, "ok-" + winner)
        self.assertIn(winner, ("a1", "a2"))

    def test_race_all_unavailable(self):
        self.assertEqual(providers.race(["a"], ["b"], lambda i: ""),
                         (None, None))

    def test_cue_caps(self):
        self.assertEqual(providers.cue_cap_tokens("gpt-4o-mini"), 1024)
        self.assertEqual(providers.cue_cap_tokens("deepseek-chat"), 1024)
        self.assertEqual(providers.cue_cap_tokens("grok-4.6"), 2048)
        self.assertEqual(providers.cue_cap_tokens("deepseek-v4-flash"), 2048)

    def test_thinking_params(self):
        self.assertEqual(
            providers.thinking_params("deepseek", "deepseek-v4-flash"),
            {"extra_body": {"thinking": {"type": "disabled"}}})
        self.assertEqual(
            providers.thinking_params("deepseek", "deepseek-v4-pro"),
            {"reasoning_effort": "low"})
        self.assertEqual(
            providers.thinking_params("openrouter", "anything"),
            {"reasoning": {"effort": "low", "exclude": True}})
        self.assertEqual(
            providers.thinking_params("claude", "claude-haiku-4-5"), {})
        self.assertIn("output_config",
                      providers.thinking_params("claude", "claude-opus-5"))
        self.assertEqual(providers.thinking_params("gemini", "x"),
                         {"thinkingLevel": "LOW"})

    def test_models_sync_due_by_default(self):
        self.assertTrue(providers.models_sync_due("deepseek-nope"))


class GroundedQATest(unittest.TestCase):
    def test_empty_dataset_refuses(self):
        conn = fresh_db()
        out = qa.answer(conn, "Best creative?")
        self.assertIsNone(out["review_id"])
        self.assertIn("Upload", out["answer"])
        conn.close()

    def test_answer_cites_uploaded_csv_first(self):
        conn = seeded_db()
        out = qa.answer(conn, "What is total spend?")
        self.assertIn("$400.00", out["answer"])
        self.assertEqual(out["sources"][0], "Uploaded CSV")
        self.assertIsNotNone(out["review_id"])
        conn.close()

    def test_ctr_counts_zero_impression_clicks(self):
        conn = seeded_db()
        ingest.insert_rows(conn, ingest.parse_csv(
            "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions\nC1,A3,hook-c,50,0,5,1\n", "meta"))
        out = qa.answer(conn, "What is the CTR?")
        # (200 + 300 + 5) / (10000 + 30000 + 0) = 1.2625% -> 1.26%.
        self.assertIn("1.26%", out["answer"])
        self.assertIn("505 clicks", out["answer"])
        conn.close()

    def test_ctr_zero_impressions_reports_zero_not_clicks(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(
            "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions\nC9,A9,hook-z,10,0,3,0\n", "meta"))
        out = qa.answer(conn, "What is the CTR?")
        # 3 clicks / 0 impressions must not render as 300.00%.
        self.assertIn("0.00%", out["answer"])
        self.assertNotIn("300.00%", out["answer"])
        conn.close()

    def test_review_to_zero_gates_export(self):
        conn = seeded_db()
        qa.answer(conn, "What is total spend?")
        with self.assertRaises(export_gate.ExportBlocked):
            export_gate.check_reviews(conn)
        for r in qa.list_reviews(conn):
            qa.mark_reviewed(conn, r["id"])
        export_gate.check_reviews(conn)  # no raise
        conn.close()


if __name__ == "__main__":
    unittest.main()

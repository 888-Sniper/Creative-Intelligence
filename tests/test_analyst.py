"""Foap Analyst deterministic acceptance tests (spec section 19).

Synthetic datasets designed to distinguish correct analysis from
plausible-looking answers. Labelled example values (1.18s / 1.02s)
are fixtures only — never real Foap performance.
"""

import json
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import analyst, ingest, schema
from creative_intel import analyst_diagnostics as diagnostics
from creative_intel import analyst_metrics as metrics
from creative_intel import creative as creative_mod


def memdb():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def row(key, **over):
    base = {"platform": "tiktok", "source": "upload", "campaign": "C",
            "adset": "", "ad_name": key, "creative_key": key,
            "missing_json": "[]"}
    base.update(over)
    return base


def res(value, state="measured"):
    return {"metric_id": "x", "definition_version": "v1", "value": value,
            "state": state, "basis": "pooled", "reasons": [],
            "numerator": 0, "denominator": 0, "unit": "percent",
            "direction": "higher_is_better"}


def ctx_for(key, metric_values, cohort_values=None, **kw):
    ctx = {"creative_key": key,
           "metrics": {m: res(v) for m, v in metric_values.items()},
           "cohort": cohort_values or {},
           "cohort_n": kw.get("cohort_n", 5),
           "exposure": kw.get("exposure", 5000),
           "spend": kw.get("spend", 10),
           "cohort_spend": kw.get("cohort_spend", [10] * 5),
           "annotation": kw.get("annotation"),
           "annotation_status": kw.get("annotation_status", "none"),
           "retention_drops": kw.get("retention_drops", []),
           "series": kw.get("series", []),
           "objective": kw.get("objective", "reach"),
           "scope": {}, "dataset_version": "t"}
    return ctx


class MetricAcceptanceTest(unittest.TestCase):
    def test_hook_rate_30_percent(self):
        rows = [row("A", impressions=1000, views_2s=300)]
        out = metrics.hook_rate_2s(rows)
        self.assertEqual(out["value"], 30.0)
        self.assertEqual(out["state"], "measured")

    def test_missing_2s_never_substitutes(self):
        rows = [row("A", impressions=1000, views_2s=0,
                    views_100=900, views_25=800,
                    missing_json=json.dumps(["views_2s"]))]
        out = metrics.hook_rate_2s(rows)
        self.assertEqual(out["state"], "unsupported")
        self.assertIsNone(out["value"])

    def test_awt_weighted_mean(self):
        rows = [row("A", video_views=100, watch_time_total_s=100.0),
                row("B", video_views=900, watch_time_total_s=2700.0)]
        awt, _pct = metrics.awt_per_view(rows)
        self.assertAlmostEqual(awt["value"], 2.8)
        self.assertEqual(awt["state"], "measured")

    def test_labelled_watch_time_difference(self):
        # Labelled fixture: group means 1.18s vs 1.02s.
        promo = [row("P", video_views=500, watch_time_total_s=590.0)]
        neutral = [row("N", video_views=500, watch_time_total_s=510.0)]
        awt_p, _ = metrics.awt_per_view(promo)
        awt_n, _ = metrics.awt_per_view(neutral)
        self.assertAlmostEqual(awt_p["value"], 1.18)
        self.assertAlmostEqual(awt_n["value"], 1.02)
        diff = awt_p["value"] - awt_n["value"]
        self.assertAlmostEqual(diff, 0.16)
        self.assertAlmostEqual(diff / awt_n["value"] * 100, 15.7,
                               places=1)

    def test_reach_never_summed(self):
        rows = [row("A", reach=500, spend=10.0),
                row("B", reach=700, spend=20.0)]
        out = metrics.cost_per_1000_reached(rows)
        self.assertEqual(out["state"], "not_applicable")
        self.assertIsNone(out["value"])

    def test_awt_excludes_watch_without_matching_count(self):
        # Row B supplies watch time but no view count: its seconds
        # must not inflate the numerator while missing from the
        # denominator. AWT = 100/100, not 300/100.
        rows = [row("A", video_views=100, watch_time_total_s=100.0),
                row("B", watch_time_total_s=200.0,
                    missing_json=json.dumps(["video_views"]))]
        awt, _pct = metrics.awt_per_view(rows)
        self.assertAlmostEqual(awt["value"], 1.0)
        self.assertTrue(awt["reasons"])

    def test_mixed_watch_bases_not_pooled(self):
        rows = [row("A", watch_time_total_s=100.0, video_views=100,
                    watch_time_basis="views"),
                row("B", watch_time_total_s=200.0, video_starts=100,
                    watch_time_basis="starts")]
        awt, _pct = metrics.awt_per_view(rows)
        self.assertIsNone(awt["value"])
        self.assertIn("bases", awt["reasons"][0])

    def test_engagement_pools_partial_rows(self):
        rows = [row("A", likes=18, comments=0, shares=0, saves=0,
                    impressions=1000),
                row("B", likes=0, comments=0, shares=0,
                    impressions=1000,
                    missing_json=json.dumps(["saves"]))]
        out = metrics.engagement_rate(rows)
        # 18 interactions over 2000 impressions — row B keeps its
        # denominator even though saves is missing there.
        self.assertAlmostEqual(out["value"], 0.9)
        self.assertEqual(out["numerator"], 18.0)
        self.assertEqual(out["denominator"], 2000.0)

    def test_engagement_unsupported_without_interactions(self):
        rows = [row("A", impressions=1000,
                    missing_json=json.dumps(
                        ["likes", "comments", "shares", "saves"]))]
        out = metrics.engagement_rate(rows)
        self.assertEqual(out["state"], "unsupported")
        self.assertIsNone(out["value"])

    def test_frequency_reach_weighted(self):
        # f=impr/reach per row: pooled frequency is 3000/1500 = 2.0.
        # Impression-weighting would give 2.5.
        rows = [row("A", frequency=1.0, impressions=1000, reach=1000),
                row("B", frequency=4.0, impressions=2000, reach=500)]
        out = metrics.frequency(rows)
        self.assertAlmostEqual(out["value"], 2.0)
        self.assertEqual(out["basis"], "reach_weighted_reported")

    def test_mixed_currencies_not_combined(self):
        rows = [row("A", spend=10.0, impressions=1000, currency="PLN"),
                row("B", spend=10.0, impressions=1000, currency="EUR")]
        out = metrics.cpm(rows)
        self.assertIsNone(out["value"])
        self.assertIn("currencies", out["reasons"][0])

    def test_daily_rows_collapse_to_creative(self):
        rows = [row("A", impressions=100, views_2s=50, date="2025-01-0%d" % d)
                for d in range(1, 11)]
        groups = metrics.compare_groups(rows, "campaign",
                                        "hook_rate_2s_impr", "views_2s",
                                        "impressions")
        self.assertEqual(groups["C"]["creative_count"], 1)
        self.assertEqual(groups["C"]["row_count"], 10)
        self.assertEqual(groups["C"]["metric"]["value"], 50.0)


class PolishImportTest(unittest.TestCase):
    def test_decimal_comma_and_aliases(self):
        conn = memdb()
        csv = ("Kampania;Kreacja;Wyświetlenia;Wydatek;Odsłony 2 s;Data\n"
               "K1;A;1000;1,18;300;12.05.2025\n")
        out = ingest.import_report(conn, csv, "tiktok")
        self.assertEqual(out["locale"], "pl")
        self.assertEqual(out["unmapped"], [])
        got = conn.execute("SELECT impressions, spend, views_2s, date"
                           " FROM ads").fetchone()
        self.assertEqual(tuple(got), (1000, 1.18, 300, "2025-05-12"))
        conn.close()

    def test_ambiguous_number_quarantined(self):
        # "1,000" inside a Polish file: thousands or decimal? The
        # row quarantines with a reason instead of guessing.
        conn = memdb()
        csv = "Kampania;Kreacja;Wydatek\nK1;A;1,000\n"
        out = ingest.import_report(conn, csv, "tiktok")
        self.assertEqual(out["inserted"], 0)
        self.assertEqual(out["quarantined"], 1)
        self.assertIn("ambiguous", out["quarantine"][0]["reason"])
        conn.close()


class RankingTest(unittest.TestCase):
    def _analysis(self, objective="reach"):
        conn = memdb()
        csv = ("Campaign,Ad,Impressions,2s views,Conversions,Spend\n"
               "C,A,5000,1500,10,100\n"
               "C,B,5000,500,0,10\n")
        ingest.import_report(conn, csv, "tiktok")
        return analyst.analyze_campaign(conn, {"campaign": ["C"]},
                                       objective)

    def test_reach_defaults_to_hook_not_cpa(self):
        analysis = self._analysis("reach")
        ranked = analyst.rank_creatives(analysis)
        self.assertEqual(ranked["rank_by"], "hook_rate_2s_impr")
        self.assertEqual(ranked["winner"]["creative_key"], "A")

    def test_explicit_kpi_controls_winner(self):
        analysis = self._analysis("reach")
        ranked = analyst.rank_creatives(analysis, rank_by="cpa")
        self.assertEqual(ranked["rank_by"], "cpa")
        self.assertEqual(ranked["winner"]["creative_key"], "A")

    def test_low_exposure_never_wins(self):
        conn = memdb()
        csv = ("Campaign,Ad,Impressions,2s views\n"
               "C,A,100,100\n"
               "C,B,5000,1000\n")
        ingest.import_report(conn, csv, "tiktok")
        analysis = analyst.analyze_campaign(conn, {"campaign": ["C"]},
                                           "reach")
        ranked = analyst.rank_creatives(analysis)
        self.assertEqual(ranked["winner"]["creative_key"], "B")
        self.assertTrue(any(e["creative_key"] == "A"
                            for e in ranked["excluded"]))
        conn.close()

    def test_scope_change_recomputes(self):
        conn = memdb()
        csv = ("Campaign,Ad,Impressions,2s views\n"
               "C1,A,1000,900\n"
               "C2,B,1000,100\n")
        ingest.import_report(conn, csv, "tiktok")
        first = analyst.analyze_campaign(conn, {"campaign": ["C1"]},
                                        "reach")
        second = analyst.analyze_campaign(conn, {"campaign": ["C2"]},
                                         "reach")
        def hook(analysis):
            return analysis["creatives"][0]["metrics"][
                "hook_rate_2s_impr"]["value"]
        self.assertEqual(hook(first), 90.0)
        self.assertEqual(hook(second), 10.0)
        conn.close()


class DiagnosticsTest(unittest.TestCase):
    COHORT = {"hook_rate_2s_impr": [30.0] * 6,
              "hook_rate_3s_impr": [20.0] * 6,
              "quartile_25_impr": [15.0] * 6,
              "quartile_50_impr": [8.0] * 6,
              "completion_impr": [4.0] * 6,
              "awt_per_view": [2.0] * 6,
              "vtr": [4.0] * 6, "cpcv": [1.0] * 6,
              "cpm": [10.0] * 6}

    def test_low_hook_triggers(self):
        ctx = ctx_for("A", {"hook_rate_2s_impr": 10.0,
                            "hook_rate_3s_impr": 8.0},
                      dict(self.COHORT), cohort_n=6,
                      annotation_status="auto")
        findings, _sup = diagnostics.evaluate_creative(ctx)
        ids = [f["finding_id"] for f in findings]
        self.assertIn("low_hook", ids)
        finding = next(f for f in findings
                       if f["finding_id"] == "low_hook")
        self.assertEqual(finding["priority"], "high")
        self.assertIn("plausible", finding["diagnosis"])

    def test_high_hook_does_not_trigger_low_hook(self):
        ctx = ctx_for("A", {"hook_rate_2s_impr": 45.0},
                      dict(self.COHORT), cohort_n=6)
        findings, _sup = diagnostics.evaluate_creative(ctx)
        self.assertNotIn("low_hook",
                         [f["finding_id"] for f in findings])

    def test_insufficient_data_is_silent(self):
        ctx = ctx_for("A", {}, {}, cohort_n=1, exposure=10)
        findings, _sup = diagnostics.evaluate_creative(ctx)
        self.assertEqual(findings, [])

    def test_compatible_rules_both_stand(self):
        # low 2s + high 3s + low 25%: low_hook fires (2s) and
        # hook_ok_body_weak fires (3s/25%) — different metrics, both
        # stand; no suppression recorded.
        cohort = dict(self.COHORT)
        ctx = ctx_for("A", {"hook_rate_2s_impr": 5.0,
                            "hook_rate_3s_impr": 40.0,
                            "quartile_25_impr": 5.0},
                      cohort, cohort_n=6)
        findings, suppressed = diagnostics.evaluate_creative(ctx)
        ids = [f["finding_id"] for f in findings]
        self.assertIn("low_hook", ids)
        self.assertIn("hook_ok_body_weak", ids)
        self.assertEqual(suppressed, [])

    def test_mutex_suppression_recorded(self):
        # q50 high + completion low + awt high: length_completion
        # wins over weak_ending; the loser is recorded, not silent.
        cohort = dict(self.COHORT)
        ctx = ctx_for("A", {"quartile_50_impr": 20.0,
                            "completion_impr": 1.0,
                            "awt_per_view": 5.0},
                      cohort, cohort_n=6)
        findings, suppressed = diagnostics.evaluate_creative(ctx)
        ids = [f["finding_id"] for f in findings]
        self.assertIn("length_completion", ids)
        self.assertNotIn("weak_ending", ids)
        self.assertIn("weak_ending", suppressed)
        winner = next(f for f in findings
                      if f["finding_id"] == "length_completion")
        self.assertTrue(any("weak_ending" in lim
                            for lim in winner["limitations"]))

    def test_hook_hold_combo_branches_exclusive(self):
        cohort = {"hook_rate_2s_impr": [30.0] * 4,
                  "hold_rate": [50.0] * 4}
        ctx = ctx_for("A", {"hook_rate_2s_impr": 10.0,
                            "hold_rate": 20.0},
                      cohort, cohort_n=4)
        finding = diagnostics.rule_hook_hold_combo(ctx)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["finding_id"], "hook_hold_low_low")

    def test_short_completion_not_crowned(self):
        cohort = {"completion_impr": [4.0] * 4,
                  "awt_per_view": [2.0] * 4}
        ctx = ctx_for("A", {"completion_impr": 15.0,
                            "awt_per_view": 0.5},
                      cohort, cohort_n=4)
        finding = diagnostics.evaluate_spec(
            ctx, next(s for s in diagnostics.RULE_SPECS
                      if s["id"] == "short_completion"))
        self.assertIsNotNone(finding)
        self.assertIn("not deep attention", finding["diagnosis"])

    def test_fatigue_needs_series(self):
        ctx = ctx_for("A", {"frequency": 5.0, "vtr": 2.0},
                      {"frequency": [2.0] * 4, "vtr": [4.0] * 4},
                      cohort_n=4)
        self.assertIsNone(diagnostics.rule_fatigue(ctx))
        series = [{"date": "2025-01-0%d" % d,
                   "frequency": res(2.0 + d),
                   "vtr": res(6.0 - d),
                   "spend": 10, "cpa": res(None, "not_applicable")}
                  for d in range(1, 5)]
        ctx["series"] = series
        finding = diagnostics.rule_fatigue(ctx)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["finding_id"], "fatigue")

    def test_brand_recall_silent_without_study(self):
        ann = creative_mod.blank_annotation()
        ann["brand_seconds"] = [{"start_s": 0.5, "end_s": 3.0}]
        ann["brand_audio_mention_s"] = 1.2
        ctx = ctx_for("A", {"quartile_50_impr": 20.0},
                      {"quartile_50_impr": [8.0] * 4}, cohort_n=4,
                      annotation=ann, annotation_status="auto")
        self.assertIsNone(diagnostics.rule_brand_recall_gap(ctx))
        summary = creative_mod.brand_evidence_summary(ann)
        self.assertIsNone(summary["recall"])
        self.assertIsNotNone(summary["opportunity"])

    def test_brand_recall_fires_with_study(self):
        ann = creative_mod.blank_annotation()
        ann["measured_recall"] = {"study": "brand-lift Q1",
                                 "value": 12.0,
                                 "assessment": "weak"}
        ctx = ctx_for("A", {"quartile_50_impr": 20.0},
                      {"quartile_50_impr": [8.0] * 4}, cohort_n=4,
                      annotation=ann, annotation_status="auto")
        finding = diagnostics.rule_brand_recall_gap(ctx)
        self.assertIsNotNone(finding)

    def test_drop_rule_stays_at_interval_resolution(self):
        ann = creative_mod.blank_annotation()
        ann["product_seconds"] = [{"start_s": 4.0, "end_s": 8.0}]
        ann["timestamp_resolution_s"] = 1.0
        drops = [{"start_s": 3.0, "end_s": 5.0, "drop_pts": 12.0,
                  "n_points": 3}]
        ctx = ctx_for("A", {}, {}, cohort_n=4, annotation=ann,
                      annotation_status="auto",
                      retention_drops=drops)
        finding = diagnostics.rule_drop_near_product(ctx)
        self.assertIsNotNone(finding)
        self.assertIn("interval resolution",
                      " ".join(finding["limitations"]))


class ClassificationTest(unittest.TestCase):
    def test_human_correction_locks_dimension(self):
        conn = memdb()
        conn.execute("INSERT INTO creatives (creative_key) VALUES ('A')")
        ann = creative_mod.set_classification(
            conn, "A", "message_class", "promotional",
            evidence={"t_span": [0, 3], "confidence": 0.9})
        self.assertEqual(ann["message_class"], "promotional")
        self.assertEqual(ann["confirmed"]["message_class"],
                         "promotional")
        # Later auto save must not silently overwrite it.
        auto = creative_mod.blank_annotation()
        auto["message_class"] = "neutral"
        creative_mod.save_annotation(conn, "A", auto)
        stored = json.loads(conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key='A'"
            ).fetchone()[0])
        self.assertEqual(stored["message_class"], "promotional")
        conn.close()

    def test_invalid_value_rejected(self):
        conn = memdb()
        with self.assertRaises(ValueError):
            creative_mod.set_classification(conn, "A", "message_class",
                                            "salesy")
        conn.close()

    def test_recall_needs_study(self):
        conn = memdb()
        with self.assertRaises(ValueError):
            creative_mod.set_classification(
                conn, "A", "message_class", "neutral",
                measured_recall={"value": 3.0})
        conn.close()


class PolishJourneyTest(unittest.TestCase):
    """Spec section 20: the seven-turn Foap conversation end to end."""

    def setUp(self):
        from creative_intel import analyst_chat as chat
        self.chat = chat
        self.conn = memdb()
        csv = ("Campaign,Ad,Impressions,2s views,3s views,25% views,"
               "50% views,Completions,Watch time,Video views,Spend,"
               "Link clicks,Message\n"
               "C,A,5000,1500,1200,900,500,300,5900,5000,50,40,"
               "promotional\n"
               "C,B,5000,500,400,300,150,80,5100,5000,50,10,neutral\n"
               "C,C,5000,200,150,120,60,30,3000,5000,50,5,neutral\n")
        ingest.import_report(self.conn, csv, "tiktok")
        self.scope = {"campaign": ["C"]}
        self.conv = None

    def tearDown(self):
        self.conn.close()

    def turn(self, question, **kw):
        kw.setdefault("scope", self.scope)
        out = self.chat.answer_turn(
            self.conn, "e1", question, conversation_id=self.conv,
            **kw)
        self.conv = out["conversation_id"]
        return out

    def test_full_journey(self):
        t1 = self.turn("Tu masz dane z kampanii, wylicz mi 2s hook "
                       "rate dla każdej kreacji. Dodaj analizę kreatywną "
                       "i wnioski dotyczące najlepszych i najgorszych "
                       "kreacji. Celem był reach.")
        self.assertEqual(t1["language"], "pl")
        self.assertEqual(t1["task"], "full_analysis")
        self.assertIn("| A |", t1["text"])
        self.assertIn("| B |", t1["text"])
        self.assertIn("30,0%", t1["text"])
        self.assertIn("views_2s", t1["text"])

        t2 = self.turn("Takie spisałem wnioski, napisz mi kilka punktów "
                       "z rekomendacjami do kolejnej kampanii oraz co "
                       "warto jeszcze przetestować.")
        self.assertEqual(t2["task"], "recommendations")
        self.assertIn("notatki analityka", t2["text"])

        t3 = self.turn("Ogranicz się do 3 punktów.")
        self.assertEqual(t3["task"], "condense")
        self.assertEqual(t3["payload"]["condensed_to"], 3)
        points = [ln for ln in t3["text"].splitlines()
                  if len(ln) > 2 and ln[0].isdigit()]
        self.assertEqual(len(points), 3)

        t4 = self.turn("I tak samo co przetestować zrób.")
        self.assertEqual(t4["task"], "condense")
        self.assertIn("tests", t4["payload"])
        self.assertEqual(len(t4["payload"]["tests"]), 3)

        t5 = self.turn("Napisz mi lepiej ten nagłówek: Mówienie do "
                       "kamery i produkt wygrywają uwagę.")
        self.assertEqual(t5["task"], "headline")
        self.assertIn("Mówienie do kamery", t5["text"])

        t6 = self.turn("Daj mi AVG Watch Time dla kreacji neutralnych "
                       "i promocyjnych.")
        self.assertEqual(t6["task"], "group_awt")
        groups = t6["payload"]["group_awt"]
        self.assertAlmostEqual(groups["promotional"]["awt"]["value"],
                               1.18)
        self.assertAlmostEqual(groups["neutral"]["awt"]["value"], 0.81)
        self.assertIn("1,18", t6["text"])

        t7 = self.turn("Pokaż mi teraz watch time dla wszystkich "
                       "kreacji.")
        self.assertEqual(t7["task"], "all_watchtime")
        self.assertIn("| A |", t7["text"])
        self.assertIn("| B |", t7["text"])
        self.assertIn("promotional", t7["text"])

        # One history, seven assistant turns, owner-scoped.
        history = self.chat.assistant_history(self.conn, self.conv)
        self.assertEqual(len(history), 7)
        with self.assertRaises(ValueError):
            self.chat.get_conversation(self.conn, "e2", self.conv)

    def test_scope_change_recomputes_visibly(self):
        t1 = self.turn("Wylicz 2s hook rate.", scope={"campaign": ["C"]})
        self.assertEqual(t1["task"], "full_analysis")
        t2 = self.turn("A teraz dla nieistniejącej kampanii.",
                       scope={"campaign": ["ZZZ"]})
        self.assertIn("Brak danych", t2["text"])
        conv = self.chat.get_conversation(self.conn, "e1", self.conv)
        self.assertEqual(conv["scope"], {"campaign": ["ZZZ"]})


if __name__ == "__main__":
    unittest.main()

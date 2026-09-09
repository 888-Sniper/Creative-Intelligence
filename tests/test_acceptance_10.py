"""Final 10/10 acceptance gates: one deterministic dataset with
overlapping campaigns/markets/verticals proves every closure item.

Gates (from the closure audit):
 1. Beauty + Spain gives the identical scoped population in
    Overview, Creatives, Ask, Compare and Reports.
 2. A creative in Spain + France shows Spain-only KPIs under a
    Spain filter.
 3. A creative in Campaign A + B shows Campaign-A-only KPIs when
    Campaign A is selected.
 4. CPA/CPC/CPM with missing denominators display n/a and rank last.
 5. All-null candidates produce no winner.
 6. Ask answers early-product VTR, length, CTA, funnel, market,
    top-vs-bottom, retention and structure from the right scope.
 7. Strict HUMAN-VERIFIED reports carry no unverified claims.
 8. XLSX holds every creative with all classifications plus raw rows.
 9. MP4 -> Run Pipeline completes extraction + stages + playback.
10. CI stays green (this file runs inside the suite it guards).
"""

import base64
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import (benchmarks, creative, ingest, providers, qa,  # noqa: E402
                            retention, schema)
from creative_intel.benchmarks import Scope  # noqa: E402
import server  # noqa: E402  (route-level scope threading)

ACC_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
           "Link Clicks,Conversions,Video Views,Revenue,"
           "Client,Project,Vertical,Market,Objective,Funnel Stage,Date\n"
           "CampA,A1,shared-creative,100,10000,200,10,6000,250,"
           "Foap,Proj1,Beauty,Spain,Sales,Lower,2026-08-01\n"
           "CampB,B1,shared-creative,200,20000,100,5,4000,100,"
           "Foap,Proj1,Beauty,France,Sales,Lower,2026-08-02\n"
           "CampA,A2,spain-only,50,5000,150,8,3000,200,"
           "Foap,Proj1,Beauty,Spain,Sales,Lower,2026-08-03\n"
           "CampB,B2,null-cpa,80,8000,0,0,1000,0,"
           "Foap,Proj1,Food,France,Awareness,Upper,2026-08-04\n"
           "CampC,C1,zero-creative,60,0,0,0,0,0,"
           "Foap,Proj2,Food,France,Awareness,Upper,2026-08-05\n"
           "CampD,D1,zero-creative-2,40,0,0,0,0,0,"
           "Foap,Proj2,Food,France,Awareness,Upper,2026-08-06\n")

SPAIN = Scope({"vertical": ["Beauty"], "market": ["Spain"]})


def _struct(**slots):
    base = {s: {"start_s": 0.0, "end_s": 0.0, "confidence": 0.0}
            for s in creative.STRUCTURE_SLOTS}
    base.update(slots)
    return base


def fresh_acc_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    ingest.insert_rows(conn, ingest.parse_csv(ACC_CSV, "meta"))
    for key, dur in (("shared-creative", 30.0),
                       ("spain-only", 12.0),
                       ("null-cpa", 20.0),
                       ("zero-creative", 0.0),
                       ("zero-creative-2", 0.0)):
        # insert_rows already upserts the creative row; set duration.
        conn.execute("UPDATE creatives SET duration_s=?, name=?"
                     " WHERE creative_key=?", (dur, key, key))
    shared = creative.blank_annotation()
    shared.update({
        "hook_type": "demo_open", "hook_modality": "spoken",
        "hook_confidence": 0.8, "creator_vs_branded": "creator",
        "creator_confidence": 0.8, "duration_s": 30.0,
        "brand_seconds": [{"start_s": 0.5, "end_s": 2.0}],
        "product_seconds": [{"start_s": 6.2, "end_s": 15.0}],
        "structure": _struct(
            hook={"start_s": 0.0, "end_s": 3.0, "confidence": 0.9},
            body={"start_s": 3.0, "end_s": 6.0, "confidence": 0.8},
            demo={"start_s": 6.0, "end_s": 15.0, "confidence": 0.9},
            cta={"start_s": 25.0, "end_s": 30.0, "confidence": 0.8}),
        "cta": "Shop now",
        "transcript_words": [{"w": "welcome", "t": 0.2, "level": "word"},
                             {"w": "foap", "t": 1.2, "level": "word"}],
        "brand_audio_mention_s": 1.2, "brand_audio_approx": False,
        "brand_audio_matches": [{"term": "foap", "t": 1.2,
                                 "approx": False}],
        "status": "human_verified"})
    creative.save_annotation(conn, "shared-creative", shared)
    spain = creative.blank_annotation()
    spain.update({
        "hook_type": "question", "hook_modality": "visual",
        "hook_confidence": 0.6, "creator_vs_branded": "branded",
        "creator_confidence": 0.6, "duration_s": 12.0,
        "structure": _struct(
            hook={"start_s": 0.0, "end_s": 3.0, "confidence": 0.7},
            body={"start_s": 3.0, "end_s": 10.0, "confidence": 0.7}),
        "status": "auto"})
    creative.save_annotation(conn, "spain-only", spain)
    creative.save_annotation(conn, "null-cpa", creative.blank_annotation())
    conn.execute("UPDATE creatives SET status='human_verified'"
                 " WHERE creative_key='shared-creative'")
    conn.executemany(
        "INSERT INTO retention (creative_key, t_sec, retention_pct)"
        " VALUES (?, ?, ?)",
        [("shared-creative", t, p) for t, p in
         [(0, 100), (3, 98), (6, 95), (9, 80), (12, 78), (15, 77),
          (18, 76), (21, 75), (24, 74), (27, 73), (30, 72)]] +
        [("spain-only", t, p) for t, p in
         [(0, 100), (3, 99), (6, 95), (9, 91), (12, 90)]])
    conn.commit()
    return conn


class ScopeObjectTest(unittest.TestCase):
    def test_axes_all_blank_case_insensitive(self):
        scope = Scope({"vertical": ["Beauty"], "market": ["all", ""],
                       "platform": "Meta"})
        self.assertEqual(scope.axes["vertical"], ["Beauty"])
        self.assertEqual(scope.axes["platform"], ["Meta"])
        self.assertNotIn("market", scope.axes)
        self.assertFalse(scope.is_empty())
        self.assertTrue(Scope().is_empty())

    def test_from_query_and_payload_agree(self):
        from_q = Scope.from_query({"vertical": ["Beauty"],
                                   "market": ["Spain"],
                                   "project": ["Proj1"]})
        from_p = Scope.from_payload({"filters": {"vertical": ["Beauty"],
                                                 "market": ["Spain"],
                                                 "project": ["Proj1"]}})
        self.assertEqual(from_q.normalized(), from_p.normalized())
        self.assertIn("include_projects", from_q.normalized())

    def test_from_query_ignore(self):
        scope = Scope.from_query({"campaigns": ["CampA"],
                                  "market": ["Spain"]},
                                 ignore=("campaign", "campaigns"))
        self.assertNotIn("campaign", scope.axes)
        self.assertEqual(scope.axes["market"], ["Spain"])

    def test_match_and_sql_agree_on_columns(self):
        conn = fresh_acc_db()
        try:
            scope = Scope({"market": ["spain"]})
            clause, params = scope.sql()
            cols = [c[0] for c in conn.execute(
                "SELECT * FROM ads LIMIT 0").description]
            sql_keys = {(r[0], r[1]) for r in conn.execute(
                "SELECT creative_key, campaign FROM ads WHERE %s" % clause,
                params).fetchall()}
            py_rows = [dict(zip(cols, v)) for v in conn.execute(
                "SELECT * FROM ads").fetchall()]
            py_keys = {(r["creative_key"], r["campaign"]) for r in py_rows
                       if scope.match(r)}
            self.assertEqual(sql_keys, py_keys)
        finally:
            conn.close()

    def test_describe(self):
        self.assertEqual(Scope().describe(), "All data")
        self.assertIn("Spain", SPAIN.describe())


class Gate1ScopeParityTest(unittest.TestCase):
    """Beauty + Spain: identical population on every surface."""

    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_overview_campaigns_scoped(self):
        per = benchmarks.campaign_kpis(self.conn,
                                       filters=SPAIN.normalized())
        self.assertEqual(sorted(per), ["CampA"])
        self.assertEqual(per["CampA"]["spend"], 150.0)

    def test_creatives_scoped(self):
        rows = benchmarks._creative_rows(self.conn, "CampA", scope=SPAIN)
        keys = sorted(r["creative_key"] for r in rows)
        self.assertEqual(keys, ["shared-creative", "spain-only"])
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        self.assertEqual(shared["spend"], 100.0)
        self.assertEqual(shared["conversions"], 10)
        scoped_out = benchmarks._creative_rows(self.conn, "CampB",
                                               scope=SPAIN)
        self.assertEqual(scoped_out, [])

    def test_ask_scoped(self):
        out = qa.answer(self.conn, "What is total spend?", scope=SPAIN)
        self.assertIn("$150.00", out["answer"])
        self.assertNotIn("CampB", out["answer"])
        self.assertEqual(out["scope"], SPAIN.describe())

    def test_compare_campaigns_scoped(self):
        got = server.expert2_compare_route(
            self.conn, {"rank_by": ["cpa"], "market": ["Spain"],
                        "vertical": ["Beauty"]})
        self.assertEqual(sorted(got["kpis"]), ["CampA"])
        self.assertEqual(got["scope"], SPAIN.describe())

    def test_report_scoped(self):
        rep = benchmarks.build_report(self.conn, ["CampA", "CampB"],
                                      ["cpa", "ctr"], None, "one-pager",
                                      filters=SPAIN)
        self.assertIn("CampA", rep["markdown"])
        self.assertNotIn("CampB", rep["markdown"])
        self.assertIn("Scope:", rep["markdown"])
        self.assertEqual(rep["deck"]["scope"], SPAIN.describe())


class Gate2MarketIsolationTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_spain_only_kpis_for_shared_creative(self):
        rows = benchmarks._creative_rows(
            self.conn, "CampA", scope={"market": ["Spain"]})
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        # France row (200 spend / 5 conv) must not blend in.
        self.assertEqual(shared["spend"], 100.0)
        self.assertEqual(shared["cpa"], 10.0)
        self.assertEqual(shared["market"], "Spain")

    def test_france_only_kpis(self):
        rows = benchmarks._creative_rows(
            self.conn, "CampB", scope={"market": ["France"]})
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        self.assertEqual(shared["spend"], 200.0)
        self.assertEqual(shared["cpa"], 40.0)


class Gate3CampaignIsolationTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_campaign_a_only(self):
        rows = benchmarks._creative_rows(self.conn, "CampA")
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        self.assertEqual((shared["spend"], shared["conversions"],
                          shared["cpa"]), (100.0, 10, 10.0))

    def test_campaign_b_only(self):
        rows = benchmarks._creative_rows(self.conn, "CampB")
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        self.assertEqual((shared["spend"], shared["conversions"],
                          shared["cpa"]), (200.0, 5, 40.0))

    def test_scope_campaign_axis(self):
        rows = benchmarks._creative_rows(
            self.conn, "CampA", scope={"campaign": ["CampA"]})
        self.assertEqual(len(rows), 2)
        rows = benchmarks._creative_rows(
            self.conn, "CampA", scope={"campaign": ["CampB"]})
        self.assertEqual(rows, [])


class Gate4NullRanksLastTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_null_cpa_campaign_ranks_last(self):
        comp = benchmarks.compare_campaigns(self.conn, ["CampB", "CampC"],
                                            rank_by="cpa")
        self.assertIsNone(comp["kpis"]["CampC"]["cpa"])
        self.assertEqual(comp["ranking"], ["CampB", "CampC"])
        self.assertEqual(comp["why"]["top"], "CampB")

    def test_null_cpc_displays_and_sorts(self):
        rows = benchmarks._creative_rows(self.conn, "CampB")
        nulls = next(r for r in rows if r["creative_key"] == "null-cpa")
        # 8000 impressions but zero clicks/conversions: CPC and CPA
        # are uncomputable (None, never false zero); CPM is fine.
        self.assertIsNone(nulls["cpc"])
        self.assertIsNone(nulls["cpa"])
        self.assertEqual(nulls["cpm"], 10.0)
        self.assertEqual(benchmarks._show(None), "n/a")

    def test_zero_impression_cpm_is_none(self):
        comp = benchmarks.compare_campaigns(self.conn, ["CampC"],
                                            rank_by="cpm")
        self.assertIsNone(comp["kpis"]["CampC"]["cpm"])


class Gate5NoWinnerTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_all_null_cpa_has_no_winner(self):
        comp = benchmarks.compare_campaigns(self.conn, ["CampC", "CampD"],
                                            rank_by="cpa")
        self.assertIsNone(comp["why"]["top"])
        self.assertIsNone(comp["why"]["bottom"])
        self.assertTrue(any("Insufficient data" in d
                            for d in comp["why"]["differences"]))

    def test_report_says_no_winner(self):
        rep = benchmarks.build_report(self.conn, ["CampC", "CampD"],
                                      ["cpa"], None, "one-pager")
        self.assertIn("No winner", rep["markdown"])


class Gate6AskParityTest(unittest.TestCase):
    """Every spec question family answers from the right scope."""

    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def _ask(self, question, scope=None):
        out = qa.answer(self.conn, question, scope=scope)
        self.assertTrue(out["answer"] and out["answer"] != "—",
                        "empty answer for %r" % question)
        return out["answer"]

    def test_spend_scoped(self):
        text = self._ask("What is total spend?", SPAIN)
        self.assertIn("$150.00", text)

    def test_early_product_vtr(self):
        text = self._ask("Does early product appearance improve VTR?",
                         SPAIN)
        self.assertIn("VTR", text)
        # shared-creative shows product at 6.2s (late); nothing is
        # early, so the blended fallback names the scoped rows.
        self.assertIn("shared-creative", text)

    def test_video_length(self):
        text = self._ask("How do video lengths perform?", SPAIN)
        self.assertIn("15-30s", text)
        self.assertIn("<=15s", text)

    def test_cta(self):
        text = self._ask("Do CTAs lift performance?", SPAIN)
        self.assertIn("with CTA", text)
        self.assertIn("without CTA", text)

    def test_funnel(self):
        text = self._ask("Which funnel stage wins?", SPAIN)
        self.assertIn("Lower", text)

    def test_market(self):
        text = self._ask("Which market performs best?")
        self.assertIn("Spain", text)
        self.assertIn("France", text)

    def test_top_vs_bottom(self):
        text = self._ask("Compare top vs bottom creatives")
        self.assertIn("Top 20%", text)
        self.assertIn("Bottom 20%", text)

    def test_retention(self):
        text = self._ask("Where do we lose viewers?", SPAIN)
        self.assertIn("curves in scope", text)

    def test_structure(self):
        text = self._ask("Which structure slots are annotated?", SPAIN)
        self.assertIn("demo", text)

    def test_hook(self):
        text = self._ask("Which hook wins?", SPAIN)
        self.assertIn("demo_open", text)

    def test_empty_scope_says_so(self):
        out = qa.answer(self.conn, "What is total spend?",
                        scope={"market": ["Germany"]})
        self.assertIn("No uploaded rows match", out["answer"])


class Gate7StrictHumanTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_strict_report_is_verified_only(self):
        rep = benchmarks.build_report(self.conn, ["CampA"], ["cpa"],
                                      None, "deck", strict_human=True)
        deck = rep["deck"]
        self.assertTrue(deck["learnings_verified"])
        self.assertTrue(all(deck["learnings_verified"]))
        self.assertTrue(all(deck["recommendations_verified"]))
        blob = " ".join(deck["learnings"] + deck["recommendations"])
        # The only verified creative is shared-creative (demo_open);
        # the auto spain-only/question label must not appear.
        self.assertNotIn("question", blob)

    def test_strict_nulls_unverified_contention(self):
        extras = benchmarks._report_extras(self.conn, ["CampB"],
                                           strict_human=True)
        best = extras["per_campaign"]["CampB"]["best"]
        # CampB rows: shared-creative (verified, in CampB) and
        # null-cpa (auto). Verified-only contention keeps the
        # verified winner, never the auto one.
        if best is not None:
            self.assertTrue(best["verified"])


class Gate8XlsxCompletenessTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def _sheets(self):
        rep = benchmarks.build_report(self.conn, ["CampA", "CampB"],
                                      ["cpa", "ctr"], None, "xlsx")
        blob = base64.b64decode(rep["xlsx_b64"])
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        self.assertIn("xl/workbook.xml", names)
        strings = []
        if "xl/sharedStrings.xml" in names:
            import re
            xml = zf.read("xl/sharedStrings.xml").decode("utf-8")
            strings = re.findall(r"<t[^>]*>(.*?)</t>", xml)
        return zf, names, strings

    def test_all_creatives_has_every_classification(self):
        _zf, names, strings = self._sheets()
        joined = "\n".join(strings)
        for header in ("client", "project", "campaign", "platform",
                       "vertical", "market", "funnel", "objective",
                       "date", "creative", "spend", "impressions",
                       "clicks", "conversions", "video_views", "revenue",
                       "cpm", "vtr", "ctr", "cpc", "cpa", "roas",
                       "hook_type", "hook_modality", "creator_vs_branded",
                       "duration_s", "brand_first_visible_s",
                       "product_first_visible_s", "logo_first_visible_s",
                       "brand_audio_mention_s", "brand_audio_approx",
                       "cta", "supers", "voiceover",
                       "editing_pace_cuts_per_min", "structure",
                       "status", "human_verified"):
            self.assertIn(header, joined, "missing XLSX column %s" % header)
        # Every creative is present, with its hook classification.
        for key in ("shared-creative", "spain-only", "null-cpa"):
            self.assertIn(key, joined)
        self.assertIn("demo_open", joined)
        self.assertIn("spoken", joined)
        self.assertTrue(any(n.startswith("xl/worksheets/sheet")
                            for n in names))

    def test_raw_performance_sheet_has_canonical_rows(self):
        _zf, _names, strings = self._sheets()
        joined = "\n".join(strings)
        for token in ("CampA", "CampB", "A1", "B1", "shared-creative",
                      "creative_key", "funnel_stage"):
            self.assertIn(token, joined,
                          "raw sheet missing %s" % token)


class Gate9PipelineTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()
        self.tmp = tempfile.mkdtemp(prefix="acc-media-")
        for key in ("pipe-creative", "real-creative"):
            self.conn.execute(
                "INSERT INTO creatives (creative_key, platform, name)"
                " VALUES (?, 'meta', ?)", (key, key))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _upload(self, key, blob, filename, mime):
        return server.apply_action(
            self.conn, "media-upload",
            {"creative_key": key, "filename": filename,
             "content_b64": base64.b64encode(blob).decode(),
             "mime": mime}, providers.Providers(), media_dir=self.tmp)

    def test_mp4_pipeline_end_to_end(self):
        from creative_intel import media as media_mod
        from creative_intel import video as video_mod
        if video_mod.have_ffmpeg():
            # Fake bytes are not decodable: the real-mp4 test below
            # covers the ffmpeg-present path instead.
            self.skipTest("needs a no-ffmpeg host")
        blob = (b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42"
                b"\x00" * 2048)
        saved = self._upload("pipe-creative", blob, "clip.mp4",
                             "video/mp4")
        self.assertTrue(saved["url"].startswith("/media/"))
        prov = providers.Providers()
        self.assertEqual(prov.mode, "mock")
        got = server.apply_action(
            self.conn, "pipeline", {"creative_key": "pipe-creative",
                                    "brand_terms": ["Foap"]},
            prov, media_dir=self.tmp)
        stages = [s["stage"] for s in got["stages"]]
        for expected in ("ingest", "transcribe", "frame-sample",
                         "vision-annotate", "llm-structure"):
            self.assertIn(expected, stages)
        self.assertTrue(got["annotation"])
        # Media playback: stored bytes round-trip byte-identical.
        back, mime, _name = media_mod.load_bytes(
            self.conn, self.tmp, saved["url"][len("/media/"):])
        self.assertEqual(back, blob)
        self.assertEqual(mime, "video/mp4")

    def test_real_mp4_extracts_when_ffmpeg_present(self):
        from creative_intel import video as video_mod
        if not video_mod.have_ffmpeg():
            self.skipTest("needs ffmpeg")
        import subprocess
        src = os.path.join(self.tmp, "src.mp4")
        # 7s: frame extraction (1 frame / 3s) yields multiple frames;
        # a ~1s clip yields zero frames at that rate on real ffmpeg.
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=7",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=7",
             "-pix_fmt", "yuv420p", "-shortest", src],
            check=True, timeout=120)
        with open(src, "rb") as f:
            blob = f.read()
        self._upload("real-creative", blob, "real.mp4", "video/mp4")
        got = server.apply_action(
            self.conn, "pipeline", {"creative_key": "real-creative",
                                    "brand_terms": ["Foap"]},
            providers.Providers(), media_dir=self.tmp)
        stages = [s["stage"] for s in got["stages"]]
        self.assertIn("transcribe", stages)
        self.assertIn("llm-structure", stages)
        derived = os.path.join(self.tmp, "derived")
        names = sorted(e.name for e in os.scandir(derived))
        self.assertTrue(any(n.endswith(".wav") for n in names),
                        "no extracted audio in %s" % names)
        self.assertTrue(any(n.endswith(".jpg") for n in names),
                        "no extracted frames in %s" % names)


class AudioTimingHonestyTest(unittest.TestCase):
    def test_word_level_is_exact(self):
        found = creative.brand_audio_mentions(
            [{"w": "foap", "t": 1.2, "level": "word", "end": 1.5}],
            ["Foap"])
        self.assertEqual(found["brand_audio_mention_s"], 1.2)
        self.assertFalse(found["brand_audio_approx"])
        self.assertFalse(found["matches"][0]["approx"])

    def test_segment_level_is_approximate(self):
        found = creative.brand_audio_mentions(
            [{"w": "welcome to foap, discover more", "t": 3.2,
              "end": 5.7, "level": "segment"}],
            ["Foap"])
        self.assertEqual(found["brand_audio_mention_s"], 3.2)
        self.assertTrue(found["brand_audio_approx"])
        match = found["matches"][0]
        self.assertTrue(match["approx"])
        self.assertEqual(match["end"], 5.7)

    def test_fill_marks_groq_segments(self):
        out = []
        providers.LiveStt._fill_timings(
            out, [{"text": "hello foap", "start": 3.2, "end": 5.7}],
            level="segment")
        self.assertEqual(out[0]["level"], "segment")
        self.assertEqual(out[0]["end"], 5.7)


class RetentionIntelligenceTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_drop_events_link_to_elements(self):
        evs = retention.drop_events(self.conn, "shared-creative")
        self.assertTrue(evs)
        # Steepest first: the 6-9s demo plunge dominates.
        self.assertGreaterEqual(evs[0]["drop_pts"], 10.0)
        self.assertEqual(evs[0]["segment"], "demo")
        self.assertEqual(evs[0]["seek_s"], evs[0]["start_s"])
        el = evs[0]["element"]
        self.assertEqual(el["slot"], "demo")
        self.assertTrue(el["product_demo"])
        self.assertFalse(el["brand_visible"])

    def test_patterns_aggregate_across_videos(self):
        pats = retention.patterns(self.conn, SPAIN)
        self.assertEqual(pats["scope"], SPAIN.describe())
        self.assertEqual(pats["n_creatives"], 2)
        self.assertTrue(pats["patterns"])
        demo = next(p for p in pats["patterns"] if p["slot"] == "demo")
        self.assertGreaterEqual(demo["n_creatives"], 1)
        self.assertIn("shared-creative", demo["examples"])

    def test_patterns_respect_scope(self):
        pats = retention.patterns(self.conn, {"market": ["France"]})
        keys = {e["creative_key"] for e in pats["events"]}
        # spain-only has no France rows: excluded from the population.
        self.assertNotIn("spain-only", keys)
        self.assertIn("shared-creative", keys)

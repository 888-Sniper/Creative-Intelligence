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
from ci_backend import actions as server  # noqa: E402  (shared builders)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
           "CampA,A3,france-offer,30,3000,30,0,500,0,"
           "Foap,Proj1,Beauty,France,Sales,Lower,2026-08-07\n"
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
        "creator_confidence": 0.8, "edit_style": "product_demo",
        "edit_confidence": 0.8, "duration_s": 30.0,
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
        "creator_confidence": 0.6, "edit_style": "talking_head",
        "edit_confidence": 0.6, "duration_s": 12.0,
        "structure": _struct(
            hook={"start_s": 0.0, "end_s": 3.0, "confidence": 0.7},
            body={"start_s": 3.0, "end_s": 10.0, "confidence": 0.7}),
        "status": "auto"})
    creative.save_annotation(conn, "spain-only", spain)
    creative.save_annotation(conn, "null-cpa", creative.blank_annotation())
    offer = creative.blank_annotation()
    offer.update({"hook_type": "offer", "hook_modality": "text",
                  "hook_confidence": 0.6, "creator_vs_branded": "hybrid",
                  "creator_confidence": 0.6, "edit_style": "montage",
                  "edit_confidence": 0.6, "duration_s": 18.0})
    creative.save_annotation(conn, "france-offer", offer)
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
        self.assertEqual(sorted(r["creative_key"] for r in rows),
                         ["france-offer", "shared-creative", "spain-only"])
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


_SRV = {}


def _test_port():
    """Lazily-built shared TestClient over a fixture snapshot.

    Module-level and lazy so HTTP tests pass regardless of the
    alphabetical class order unittest imposes; torn down by
    tearDownModule. Mutating tests must leave the snapshot clean.
    """
    if "client" not in _SRV:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        import tempfile
        live = fresh_acc_db()
        path = tempfile.NamedTemporaryFile(suffix=".db",
                                           delete=False).name
        disk = sqlite3.connect(path)
        schema.init_db(disk)
        for sql in live.iterdump():
            if sql.startswith("INSERT"):
                disk.execute(sql)
        disk.commit()
        live.close()
        disk.close()
        client = make_client(path)
        client.headers.update(mint_admin(path))
        _SRV.update(client=client, path=path)
    return _SRV["client"]


def tearDownModule():
    if "client" in _SRV:
        os.unlink(_SRV["path"])
        _SRV.clear()


def _fetch(path, timeout=10):
    client = _test_port()
    r = client.get(path)
    assert r.status_code == 200, (path, r.text)
    return r.json()


def _post(path, body, timeout=10):
    client = _test_port()
    r = client.post(path, json=body)
    assert r.status_code == 200, (path, r.text)
    return r.json()


class RouteScopeIntegrationTest(unittest.TestCase):
    """The real HTTP routes (not just the helpers) honour Scope.

    Regression cover for the round where /api/campaigns and
    /api/benchmarks used the old helper without the campaign axis.
    """

    def _get(self, path):
        return _fetch(path)

    def test_campaigns_route_scopes_by_campaign(self):
        got = self._get("/api/campaigns?campaign=CampA")
        self.assertEqual(sorted(got), ["CampA"])
        self.assertEqual(got["CampA"]["spend"], 180.0)

    def test_campaigns_route_scopes_by_market(self):
        got = self._get("/api/campaigns?market=Spain")
        self.assertEqual(sorted(got), ["CampA"])

    def test_benchmarks_route_scopes_by_campaign(self):
        got = self._get("/api/benchmarks?group_by=platform&campaign=CampA")
        # All rows are meta, so only the spend proves the scope:
        # CampA = 180, whole dataset = 560.
        self.assertEqual(sorted(got), ["meta"])
        self.assertEqual(got["meta"]["spend"], 180.0)

    def test_benchmarks_route_scopes_by_market(self):
        got = self._get("/api/benchmarks?group_by=campaign&market=Spain")
        self.assertEqual(sorted(got), ["CampA"])

    def test_curve_route_serves_points_and_markers(self):
        got = self._get("/api/retention/curve?creative_key=shared-creative")
        self.assertEqual(len(got["points"]), 11)
        self.assertEqual(got["markers"]["product_s"], 6.2)
        self.assertEqual(got["markers"]["brand_s"], 0.5)
        self.assertEqual(got["markers"]["cta_s"], 25.0)
        self.assertEqual(got["markers"]["hook"],
                         {"start_s": 0.0, "end_s": 3.0})


class WhyAnalysisScopeTest(unittest.TestCase):
    """The campaign why-analysis reads the scoped population."""

    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_elements_exclude_out_of_scope_mix(self):
        scoped = benchmarks._campaign_elements(self.conn, "CampA",
                                               {"market": ["Spain"]})
        self.assertNotIn("offer", scoped["hook_types"])
        self.assertNotIn("hybrid", scoped["creator_modes"])
        full = benchmarks._campaign_elements(self.conn, "CampA")
        self.assertIn("offer", full["hook_types"])
        self.assertIn("hybrid", full["creator_modes"])

    def test_compare_why_no_french_contamination(self):
        full = benchmarks.compare_campaigns(
            self.conn, ["CampA", "CampB"], rank_by="cpa",
            filters={"vertical": ["Beauty"]})
        self.assertTrue(any("offer" in d
                            for d in full["why"]["differences"]))
        scoped = benchmarks.compare_campaigns(
            self.conn, ["CampA", "CampB"], rank_by="cpa",
            filters={"market": ["Spain"]})
        self.assertFalse(any("offer" in d
                             for d in scoped["why"]["differences"]))
        self.assertFalse(any("hybrid" in d
                             for d in scoped["why"]["differences"]))


class ReportBenchmarkScopeTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_benchmark_scoped_by_default(self):
        rep = benchmarks.build_report(self.conn, ["CampA"], ["cpa"],
                                      "platform", "deck", filters=SPAIN)
        bench = rep["deck"]["benchmark"]
        self.assertEqual(bench["meta"]["spend"], 150.0)
        self.assertIn("scoped", rep["deck"]["benchmark_scope"])
        self.assertIn("## Benchmark (scoped", rep["markdown"])

    def test_benchmark_global_opt_out(self):
        rep = benchmarks.build_report(self.conn, ["CampA"], ["cpa"],
                                      "platform", "deck", filters=SPAIN,
                                      benchmark_scope="global")
        bench = rep["deck"]["benchmark"]
        self.assertEqual(bench["meta"]["spend"], 560.0)
        self.assertIn("global", rep["deck"]["benchmark_scope"])

    def test_metric_benchmark_scoped(self):
        rep = benchmarks.build_report(self.conn, ["CampA"], ["cpa"],
                                      "cpa", "deck", filters=SPAIN)
        self.assertEqual(rep["deck"]["benchmark"]["cpa"],
                         round(150.0 / 18, 2))


class SamplePlanTest(unittest.TestCase):
    """Full-video sample plans: dense hook window, even middle,
    guaranteed end frame, hard cap."""

    def test_thirty_second_plan(self):
        from creative_intel import video as video_mod
        self.assertEqual(
            video_mod.sample_times(30.0),
            [0, 1, 2, 3, 6, 9, 12, 15, 18, 21, 24, 27, 29.5])

    def test_end_frame_guaranteed(self):
        from creative_intel import video as video_mod
        for duration in (7.0, 15.0, 30.0, 45.0, 120.0):
            times = video_mod.sample_times(duration)
            self.assertEqual(times, sorted(set(times)))
            self.assertLessEqual(len(times), video_mod.MAX_FRAMES)
            self.assertEqual(times[0], 0)
            self.assertGreaterEqual(times[-1], duration - 0.6)
            for head in (0, 1, 2, 3):
                self.assertIn(head, times)

    def test_short_clip_stays_sane(self):
        from creative_intel import video as video_mod
        times = video_mod.sample_times(2.0)
        self.assertEqual(times[0], 0)
        self.assertGreaterEqual(times[-1], 1.4)
        self.assertLessEqual(len(times), video_mod.MAX_FRAMES)


class VisionBatchingTest(unittest.TestCase):
    """LiveVision sends every image in MAX_IMAGES batches."""

    def test_batches_cover_all_images_in_order(self):
        seen = []

        class Chunked(providers.LiveVision):
            def _annotate_batch(self, use, t_secs):
                seen.append((len(use), list(t_secs)))
                return [{"t_sec": t, "label": "stub", "brand_visible": False,
                         "product_visible": False, "logo_visible": False,
                         "text_overlay": "", "cta_visible": False,
                         "end_frame": False, "cut": False,
                         "confidence": 0.9} for t in t_secs]

        vision = Chunked([("x", "y", "active")])
        frames = [{"t_sec": float(t)} for t in range(13)]
        labels = vision.annotate(frames, images=["img%d" % i for i in range(13)])
        self.assertEqual([n for n, _ts in seen], [6, 6, 1])
        self.assertEqual([l["t_sec"] for l in labels],
                         [float(t) for t in range(13)])

    def test_empty_images_still_fail_closed(self):
        vision = providers.LiveVision([("x", "y", "active")])
        with self.assertRaises(providers.ProviderUnavailable):
            vision.annotate([{"t_sec": 0.0}], images=[])


class LateEventCoverageTest(unittest.TestCase):
    """30s+ video with a visual event near the end, end to end.

    A fake vision adapter flags product/CTA only at t>=30s. The old
    front-loaded pipeline (10 default frames, first 6 images kept)
    could never see past ~15s; the full-video plan must surface the
    late event in the annotation with exact timing.
    """

    def setUp(self):
        from creative_intel import video as video_mod
        if not video_mod.have_ffmpeg():
            self.skipTest("needs ffmpeg")
        import subprocess
        self.conn = fresh_acc_db()
        self.tmp = tempfile.mkdtemp(prefix="acc-late-")
        self.clip = os.path.join(self.tmp, "late.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i", "color=c=green:s=64x64:d=35",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=35",
             "-pix_fmt", "yuv420p", "-shortest", self.clip],
            check=True, timeout=180)
        self.conn.execute(
            "INSERT INTO creatives (creative_key, platform, name)"
            " VALUES ('late-creative', 'meta', 'late-creative')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_late_product_and_cta_survive(self):
        import types
        from creative_intel import video as video_mod
        prepared = video_mod.prepare(
            self.clip, os.path.join(self.tmp, "derived"))
        self.assertGreater(len(prepared["images"]), 6)
        self.assertGreaterEqual(prepared["image_times"][-1], 33.0)

        calls = {}

        class FakeVision:
            def sample_frames(self, creative_key, every_s=3.0,
                              duration_s=30.0):
                raise AssertionError("bundle times must win")

            def annotate(self, frames, images=None):
                calls["frames"] = [f["t_sec"] for f in frames]
                calls["n_images"] = len(images or [])
                out = []
                for f in frames:
                    t = f["t_sec"]
                    out.append({"t_sec": t, "label": "test-frame",
                                "brand_visible": False,
                                "product_visible": t >= 30.0,
                                "logo_visible": False, "text_overlay": "",
                                "cta_visible": t >= 33.0,
                                "end_frame": t >= 34.0, "cut": False,
                                "confidence": 0.9})
                return out

        prov = types.SimpleNamespace(stt=providers.MockStt(),
                                     vision=FakeVision(),
                                     llm=providers.MockLlm())
        got = creative.run_pipeline(
            self.conn, "late-creative", prov,
            media={"audio": prepared["audio"],
                   "images": prepared["images"],
                   "image_times": prepared["image_times"],
                   "duration_s": prepared["duration_s"]},
            brand_terms=["Foap"])
        # Vision saw every extracted image with true timestamps.
        self.assertEqual(calls["n_images"], len(prepared["images"]))
        self.assertGreaterEqual(max(calls["frames"]), 33.0)
        ann = got["annotation"]
        product = ann["product_seconds"][0]["start_s"]
        self.assertGreaterEqual(product, 30.0)
        cta = ann["structure"]["cta"]
        self.assertGreaterEqual(cta["start_s"], 33.0)
        end = ann["structure"]["endframe"]
        self.assertGreaterEqual(end["start_s"], 34.0)
        dur = self.conn.execute(
            "SELECT duration_s FROM creatives WHERE creative_key=?",
            ("late-creative",)).fetchone()[0]
        self.assertGreaterEqual(dur, 34.0)


class CampaignKpiBestWatchTest(unittest.TestCase):
    """Campaign Best/Watch follows the selected KPI, not hard-coded CPA."""

    def test_no_hardcoded_cpa_rank(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(root, "Web", "Index.html")) as f:
            html = f.read()
        start = html.index("async function campaign_detail")
        end = html.index("async function library", start)
        body = html[start:end]
        self.assertNotIn("by_cpa", body)
        self.assertNotIn("a.metrics.cpa,true", body)
        self.assertIn("campaign-benchmark ${k.toUpperCase()}", body)
        self.assertIn("active_filters()", body)


class MultiCompareTest(unittest.TestCase):
    """Creative comparison covers 2-6 creatives, pairwise or N-way."""

    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def _datas(self, keys):
        out = {}
        for key in keys:
            rows = [dict(zip(
                ["spend", "impressions", "clicks", "conversions",
                 "video_views", "revenue"],
                r)) for r in self.conn.execute(
                "SELECT spend, impressions, clicks, conversions,"
                " video_views, revenue FROM ads WHERE creative_key=?",
                (key,)).fetchall()]
            spend = sum(r["spend"] for r in rows)
            conv = sum(r["conversions"] for r in rows)
            clicks = sum(r["clicks"] for r in rows)
            impr = sum(r["impressions"] for r in rows)
            out[key] = {
                "spend": spend, "conversions": conv,
                "cpa": round(spend / conv, 2) if conv else None,
                "ctr": round(clicks / impr, 4) if impr else None,
                "annotation": None}
        return out

    def test_n_way_names_per_metric_leaders(self):
        keys = ["shared-creative", "spain-only", "null-cpa"]
        why = server._multi_why(keys, self._datas(keys))
        # spain-only has the lowest CPA (6.25) of the converting pair.
        self.assertEqual(why["top"], "spain-only")
        self.assertTrue(any("leads on CPA" in d
                            for d in why["differences"]))

    def test_n_way_needs_two(self):
        why = server._multi_why(["only-one"], self._datas(["only-one"]))
        self.assertIsNone(why["top"])

    def test_n_way_no_data_has_no_winner(self):
        why = server._multi_why(
            ["zero-creative", "zero-creative-2"],
            {k: {"spend": 0, "conversions": 0, "cpa": None,
                 "ctr": None, "annotation": None}
             for k in ("zero-creative", "zero-creative-2")})
        self.assertIsNone(why["top"])
        self.assertTrue(any("delivery data" in d
                            for d in why["differences"]))

    def test_route_accepts_up_to_six_keys(self):
        got = _fetch(
            "/api/compare?key=shared-creative&key=spain-only&key=null-cpa")
        self.assertEqual(got["keys"],
                         ["shared-creative", "spain-only", "null-cpa"])
        self.assertEqual(got["why"]["top"], "spain-only")
        # Legacy pairwise shape is unchanged.
        pair = _fetch("/api/compare?a=shared-creative&b=spain-only")
        self.assertIn("top", pair["why"])
        self.assertIn("differences", pair["why"])

    def test_rank_creatives_follows_direction(self):
        per = {"x": {"cpa": 10.0, "ctr": 0.01, "roas": None},
               "y": {"cpa": 5.0, "ctr": 0.03, "roas": None},
               "z": {"cpa": None, "ctr": None, "roas": None}}
        ranking, winner = server._rank_creatives(["x", "y", "z"], per, "cpa")
        self.assertEqual((ranking, winner), (["y", "x", "z"], "y"))
        ranking, winner = server._rank_creatives(["x", "y", "z"], per, "ctr")
        self.assertEqual((ranking, winner), (["y", "x", "z"], "y"))
        # Missing never converts to zero: z ranks last, never first.
        ranking, winner = server._rank_creatives(["z", "x"], per, "cpa")
        self.assertEqual(winner, "x")
        ranking, winner = server._rank_creatives(
            ["z"], {"z": {"cpa": None}}, "cpa")
        self.assertIsNone(winner)
        with self.assertRaises(ValueError):
            server.build_compare(self.conn, {"rank_by": ["nonsense"]})

    def test_attribute_table_side_by_side(self):
        table = server._attribute_table({
            "x": {"hook_type": "question", "hook_modality": "spoken",
                  "creator_vs_branded": "creator", "edit_style": "ugc",
                  "duration_s": 30.0, "product_seconds": [{"start_s": 2.0}],
                  "brand_seconds": [], "logo_seconds": [],
                  "brand_audio_mention_s": 5.0, "cta": "buy now",
                  "supers": ["50% off"], "pace_cuts_per_min": 12.0,
                  "structure": {"voiceover": {"start_s": 0.0, "end_s": 3.0}},
                  "status": "human_verified"},
            "y": None})
        by_label = {row["attribute"]: row["values"] for row in table}
        self.assertEqual(len(table), 15)
        self.assertEqual(by_label["Hook type"], {"x": "question", "y": None})
        self.assertEqual(by_label["Product first appears (s)"],
                         {"x": 2.0, "y": None})
        self.assertEqual(by_label["Brand first appears (s)"],
                         {"x": None, "y": None})
        self.assertEqual(by_label["Voiceover"], {"x": "set", "y": None})
        self.assertEqual(by_label["Verification status"],
                         {"x": "human_verified", "y": None})

    def test_route_accepts_rank_by(self):
        got = _fetch("/api/compare?key=shared-creative&key=spain-only"
                     "&rank_by=ctr")
        self.assertEqual(got["rank_by"], "ctr")
        self.assertIn("ranking", got)
        self.assertIn("winner", got)
        self.assertEqual(len(got["attributes"]), 15)
        r = _test_port().get("/api/compare?key=shared-creative&rank_by=nope")
        self.assertEqual(r.status_code, 409)

    def test_route_rejects_seventh_key(self):
        query = "&".join("key=k%d" % i for i in range(7))
        r = _test_port().get("/api/compare?" + query)
        self.assertEqual(r.status_code, 409)
        self.assertIn("error", r.json())


class SavedViewsTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_save_list_retrieve(self):
        state = {"filters": {"market": ["Spain"]}, "kpi": "roas",
                 "view": "compare", "benchmark": "platform",
                 "benchmark_scope": "global", "rank_by": "roas"}
        saved = server.save_view(self.conn, "Spain ROAS", state)
        self.assertEqual(saved["name"], "Spain ROAS")
        self.assertEqual(saved["state"]["kpi"], "roas")
        self.assertEqual(saved["state"]["rank_by"], "roas")
        listed = server.list_views(self.conn)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["state"]["filters"],
                         {"market": ["Spain"]})

    def test_resave_replaces_without_duplicating(self):
        first = server.save_view(self.conn, "V", {"kpi": "cpa"})
        second = server.save_view(self.conn, "V", {"kpi": "ctr"})
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(server.list_views(self.conn)[0]["state"]["kpi"],
                         "ctr")

    def test_validation_rejects_bad_state(self):
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "", {"kpi": "cpa"})
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "V", {"kpi": "bogus"})
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "V", {"nope": 1})
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "V",
                             {"filters": {"bogus_axis": ["x"]}})
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "V",
                             {"benchmark_scope": "whenever"})
        with self.assertRaises(ValueError):
            server.save_view(self.conn, "V", {"rank_by": "spend"})

    def test_delete_roundtrip(self):
        saved = server.save_view(self.conn, "Gone", {"kpi": "cpa"})
        out = server.apply_action(self.conn, "delete-view",
                                  {"id": saved["id"]},
                                  providers.Providers())
        self.assertTrue(out["ok"])
        self.assertEqual(server.list_views(self.conn), [])
        with self.assertRaises(ValueError):
            server.apply_action(self.conn, "delete-view",
                                {"id": saved["id"]},
                                providers.Providers())

    def test_http_roundtrip(self):
        self.assertEqual(_fetch("/api/views"), [])
        saved = _post("/api/views", {"name": "HTTP view",
                                     "state": {"kpi": "vtr",
                                               "view": "benchmark"}})
        self.assertEqual(saved["state"]["kpi"], "vtr")
        listed = _fetch("/api/views")
        self.assertEqual([v["name"] for v in listed], ["HTTP view"])
        _post("/api/views/delete", {"id": saved["id"]})
        self.assertEqual(_fetch("/api/views"), [])


class ReportKpiAwarenessTest(unittest.TestCase):
    """Best/Watch/recommendations follow the report's rank KPI."""

    KPI_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
               "Link Clicks,Conversions,Revenue\n"
               "CampX,A1,cpa-champ,100,10000,200,10,100\n"
               "CampX,B1,roas-champ,100,10000,100,5,500\n"
               "CampY,Y1,nobody,50,5000,50,0,0\n")

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        schema.init_db(self.conn)
        ingest.insert_rows(self.conn, ingest.parse_csv(self.KPI_CSV, "meta"))

    def tearDown(self):
        self.conn.close()

    def test_best_follows_rank_metric(self):
        cpa = benchmarks._report_extras(self.conn, ["CampX"], rank_by="cpa")
        self.assertEqual(cpa["per_campaign"]["CampX"]["best"]["creative_key"],
                         "cpa-champ")
        self.assertEqual(cpa["per_campaign"]["CampX"]["worst"]["creative_key"],
                         "roas-champ")
        roas = benchmarks._report_extras(self.conn, ["CampX"], rank_by="roas")
        self.assertEqual(roas["per_campaign"]["CampX"]["best"]["creative_key"],
                         "roas-champ")
        self.assertEqual(roas["per_campaign"]["CampX"]["worst"]["creative_key"],
                         "cpa-champ")

    def test_recommendations_name_rank_metric(self):
        rep = benchmarks.build_report(self.conn, ["CampX"], ["roas"],
                                      None, "one-pager")
        self.assertIn("highest best-creative ROAS", rep["markdown"])
        self.assertIn("roas-champ", rep["markdown"])
        self.assertIn("(ROAS 5.0", rep["markdown"])
        rep = benchmarks.build_report(self.conn, ["CampX"], ["cpa"],
                                      None, "one-pager")
        self.assertIn("lowest best-creative CPA", rep["markdown"])
        self.assertIn("cpa-champ", rep["markdown"])

    def test_uncomputable_rank_has_no_best(self):
        extras = benchmarks._report_extras(self.conn, ["CampY"],
                                           rank_by="cpa")
        # Zero conversions anywhere: CPA is None for every creative,
        # so there is no best rather than an arbitrary pick.
        self.assertIsNone(extras["per_campaign"]["CampY"]["best"])
        self.assertIsNone(extras["per_campaign"]["CampY"]["worst"])
        # The thin single market is noted, never ranked.
        self.assertTrue(any("too early to judge" in r
                            for r in extras["recommendations"]))
        rep = benchmarks.build_report(self.conn, ["CampY"], ["cpa"],
                                      None, "one-pager")
        self.assertIn("too early to judge", rep["markdown"])

    def test_bad_rank_rejected(self):
        with self.assertRaises(ValueError):
            benchmarks._report_extras(self.conn, ["CampX"], rank_by="bogus")
        with self.assertRaises(ValueError):
            benchmarks.build_report(self.conn, ["CampX"], ["cpa"], None,
                                    "one-pager", rank_by="bogus")

    def test_explicit_rank_by_beats_kpi_order(self):
        # KPIs list Spend first (the old silent decider); the explicit
        # rank control must win either way, end to end via the route.
        payload = {"campaigns": ["CampX"],
                   "kpis": ["spend", "impressions", "roas"],
                   "format": "one-pager", "rank_by": "roas"}
        rep = server.expert2_report_route(self.conn, payload)
        best = [l for l in rep["markdown"].splitlines()
                if l.startswith("- CampX best:")]
        self.assertEqual(len(best), 1)
        self.assertIn("roas-champ", best[0])
        self.assertIn("(ROAS 5.0,", best[0])
        self.assertNotIn("CPA $", best[0])
        payload["rank_by"] = "cpa"
        rep = server.expert2_report_route(self.conn, payload)
        best = [l for l in rep["markdown"].splitlines()
                if l.startswith("- CampX best:")]
        self.assertEqual(len(best), 1)
        self.assertIn("cpa-champ", best[0])
        self.assertIn("(CPA $10.0,", best[0])
        self.assertNotIn("ROAS", best[0])

    def test_deck_best_names_rank_metric(self):
        rep = server.expert2_report_route(
            self.conn, {"campaigns": ["CampX"], "kpis": ["roas"],
                        "format": "deck", "rank_by": "roas"})
        best = rep["deck"]["creatives"]["CampX"]["best"]
        self.assertEqual(best["creative_key"], "roas-champ")
        self.assertEqual(best["roas"], 5.0)

    def test_ui_rank_control_wired(self):
        root = os.path.join(os.path.dirname(__file__), "..")
        with open(os.path.join(root, "Web", "Index.html")) as f:
            html = f.read()
        self.assertIn('id="rep-rank"', html)
        for value in ("cpa", "cpm", "ctr", "vtr", "roas"):
            self.assertIn('value="%s"' % value, html)
        self.assertIn('rank_by:$("rep-rank").value', html)


class QuartileSynthesisTest(unittest.TestCase):
    Q_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
             "Link Clicks,Conversions,Video Views,views_25,views_50,"
             "views_75,views_100,Revenue,Client,Project,Vertical,Market,"
             "Objective,Funnel Stage,Date\n"
             "QCamp,Q1,quart-creative,100,10000,200,10,6000,8000,6000,4000,"
             "2000,250,Foap,Proj1,Beauty,Spain,Sales,Lower,2026-08-01\n")

    def _db(self):
        conn = sqlite3.connect(":memory:")
        schema.init_db(conn)
        return conn

    def test_quartiles_become_curve(self):
        conn = self._db()
        try:
            ingest.insert_rows(conn, ingest.parse_csv(self.Q_CSV, "meta"))
            pts = conn.execute(
                "SELECT t_sec, retention_pct FROM retention"
                " WHERE creative_key=? ORDER BY t_sec",
                ("quart-creative",)).fetchall()
            self.assertEqual(pts, [(0.0, 100.0), (7.5, 80.0), (15.0, 60.0),
                                   (22.5, 40.0), (30.0, 20.0)])
        finally:
            conn.close()

    def test_manual_curves_win(self):
        conn = self._db()
        try:
            conn.execute("INSERT INTO retention (creative_key, t_sec,"
                         " retention_pct) VALUES ('quart-creative', 0, 99)")
            ingest.insert_rows(conn, ingest.parse_csv(self.Q_CSV, "meta"))
            pts = conn.execute(
                "SELECT t_sec, retention_pct FROM retention"
                " WHERE creative_key=?", ("quart-creative",)).fetchall()
            self.assertEqual(pts, [(0, 99)])
        finally:
            conn.close()

    def test_no_quartiles_no_curve(self):
        conn = self._db()
        try:
            ingest.insert_rows(conn, ingest.parse_csv(ACC_CSV, "meta"))
            n = conn.execute("SELECT COUNT(*) FROM retention").fetchone()[0]
            self.assertEqual(n, 0)
        finally:
            conn.close()

    def test_synth_rows_are_stamped(self):
        conn = self._db()
        try:
            ingest.upsert_rows(conn, ingest.parse_csv(self.Q_CSV, "meta"))
            sources = {r[0] for r in conn.execute(
                "SELECT DISTINCT source FROM retention").fetchall()}
            self.assertEqual(sources, {"quartile_synthesized"})
        finally:
            conn.close()

    def test_synth_refreshes_on_reimport(self):
        conn = self._db()
        try:
            ingest.upsert_rows(conn, ingest.parse_csv(self.Q_CSV, "meta"))
            first = conn.execute(
                "SELECT t_sec, retention_pct FROM retention"
                " WHERE creative_key=? ORDER BY t_sec",
                ("quart-creative",)).fetchall()
            self.assertEqual(len(first), 5)
            changed = self.Q_CSV.replace(",2000,250,", ",9000,250,", 1)
            ingest.upsert_rows(conn, ingest.parse_csv(changed, "meta"))
            pts = conn.execute(
                "SELECT t_sec, retention_pct FROM retention"
                " WHERE creative_key=? ORDER BY t_sec",
                ("quart-creative",)).fetchall()
            self.assertEqual(len(pts), 5)
            self.assertEqual(pts[-1], (30.0, 90.0))
        finally:
            conn.close()

    def test_manual_rows_survive_reimport(self):
        conn = self._db()
        try:
            ingest.upsert_rows(conn, ingest.parse_csv(self.Q_CSV, "meta"))
            conn.execute(
                "INSERT OR REPLACE INTO retention (creative_key, t_sec,"
                " retention_pct, source) VALUES ('quart-creative', 0, 99,"
                " 'manual')")
            conn.commit()
            changed = self.Q_CSV.replace(",2000,250,", ",9000,250,", 1)
            ingest.upsert_rows(conn, ingest.parse_csv(changed, "meta"))
            pts = conn.execute(
                "SELECT t_sec, retention_pct, source FROM retention"
                " WHERE creative_key=? ORDER BY t_sec",
                ("quart-creative",)).fetchall()
            # Manual point intact; the key is skipped wholesale so the
            # reimport neither overwrites it nor duplicates siblings.
            self.assertEqual(len(pts), 5)
            self.assertEqual(pts[0], (0, 99, "manual"))
            self.assertEqual(
                [p[1] for p in pts],
                [99, 80.0, 60.0, 40.0, 20.0])
        finally:
            conn.close()

    def test_migrate_adds_retention_source(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE TABLE ads (id INTEGER PRIMARY KEY, platform TEXT,"
                " source TEXT, campaign TEXT, adset TEXT, ad_name TEXT,"
                " creative_key TEXT, spend REAL, impressions INTEGER,"
                " clicks INTEGER, conversions REAL, video_views INTEGER,"
                " views_25 INTEGER, views_50 INTEGER, views_75 INTEGER,"
                " views_100 INTEGER, client TEXT, project TEXT,"
                " vertical TEXT, market TEXT, objective TEXT,"
                " funnel_stage TEXT, date TEXT, revenue REAL)")
            conn.execute(
                "CREATE TABLE retention (creative_key TEXT NOT NULL,"
                " t_sec REAL NOT NULL, retention_pct REAL NOT NULL,"
                " PRIMARY KEY (creative_key, t_sec))")
            conn.execute("INSERT INTO retention VALUES ('k', 0, 99)")
            schema.migrate(conn)
            cols = [r[1] for r in
                    conn.execute("PRAGMA table_info(retention)")]
            self.assertIn("source", cols)
            self.assertEqual(
                conn.execute("SELECT source FROM retention").fetchone()[0],
                "manual")
        finally:
            conn.close()


class EditStyleTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_taxonomy_validates(self):
        ann = creative.blank_annotation()
        ann["edit_style"] = "ugc"
        self.assertEqual(creative.validate(ann), [])
        ann["edit_style"] = "shaky-cam"
        self.assertTrue(any("edit_style" in e
                            for e in creative.validate(ann)))

    def test_benchmark_groups_by_style(self):
        bench = benchmarks.benchmark(self.conn, "edit_style")
        self.assertEqual(bench["product_demo"]["spend"], 300.0)
        self.assertIn("talking_head", bench)
        self.assertIn("montage", bench)

    def test_rows_and_xlsx_carry_style(self):
        rows = benchmarks._creative_rows(self.conn, "CampA")
        shared = next(r for r in rows
                      if r["creative_key"] == "shared-creative")
        self.assertEqual(shared["edit_style"], "product_demo")
        rep = benchmarks.build_report(self.conn, ["CampA"], ["cpa"],
                                      None, "xlsx")
        import base64
        import io
        import re
        import zipfile
        zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(rep["xlsx_b64"])))
        strings = " ".join(re.findall(
            r"<t[^>]*>(.*?)</t>",
            zf.read("xl/sharedStrings.xml").decode("utf-8")))
        self.assertIn("edit_style", strings)
        self.assertIn("product_demo", strings)

    def test_ask_answers_styles(self):
        out = qa.answer(self.conn, "Which editing style wins?", SPAIN)
        self.assertIn("product_demo", out["answer"])

    def test_compare_contrasts_style(self):
        why = server._creative_why(
            "x", "y",
            {"conversions": 5, "cpa": 10.0, "ctr": 0.02,
             "impressions": 1000,
             "annotation": {"hook_type": "question",
                            "creator_vs_branded": "creator",
                            "edit_style": "ugc"}},
            {"conversions": 5, "cpa": 12.0, "ctr": 0.02,
             "impressions": 1000,
             "annotation": {"hook_type": "question",
                            "creator_vs_branded": "creator",
                            "edit_style": "montage"}})
        self.assertTrue(any("uses style ugc" in d
                            for d in why["differences"]))

    def test_compare_why_missing_kpi_never_wins(self):
        why = server._creative_why(
            "x", "y",
            {"conversions": 0, "cpa": None, "ctr": None,
             "impressions": 1000, "annotation": {}},
            {"conversions": 5, "cpa": 12.0, "ctr": 0.02,
             "impressions": 1000, "annotation": {}})
        joined = " ".join(why["differences"])
        self.assertIn("CPA is not measurable for x", joined)
        self.assertIn("CTR is not measurable for x", joined)
        self.assertFalse(any("x leads y on CPA" in d
                             for d in why["differences"]))
        self.assertFalse(any("x leads y on CTR" in d
                             for d in why["differences"]))
        self.assertEqual(why["top"], "y")


class BrandTimingTest(unittest.TestCase):
    BT_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
              "Link Clicks,Conversions,Video Views,Revenue,Client,Project,"
              "Vertical,Market,Objective,Funnel Stage,Date\n"
              "CampB,B1,early-brand,100,10000,200,10,6000,250,"
              "Foap,Proj1,Beauty,Spain,Sales,Lower,2026-08-01\n"
              "CampB,B2,late-brand,100,10000,100,5,3000,100,"
              "Foap,Proj1,Beauty,Spain,Sales,Lower,2026-08-02\n")

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        schema.init_db(self.conn)
        ingest.insert_rows(self.conn, ingest.parse_csv(self.BT_CSV, "meta"))
        early = creative.blank_annotation()
        early.update({
            "brand_seconds": [{"start_s": 0.5, "end_s": 2.0}],
            "logo_seconds": [{"start_s": 1.0, "end_s": 2.0}],
            "transcript_words": [{"w": "foap", "t": 1.0, "level": "word"}],
            "brand_audio_mention_s": 1.0, "brand_audio_approx": False,
            "brand_audio_matches": [{"term": "foap", "t": 1.0,
                                     "approx": False}]})
        creative.save_annotation(self.conn, "early-brand", early)
        late = creative.blank_annotation()
        late.update({
            "brand_seconds": [{"start_s": 8.0, "end_s": 12.0}],
            "logo_seconds": [{"start_s": 9.0, "end_s": 12.0}],
            "transcript_words": [{"w": "foap", "t": 9.0, "level": "word"}],
            "brand_audio_mention_s": 9.0, "brand_audio_approx": False,
            "brand_audio_matches": [{"term": "foap", "t": 9.0,
                                     "approx": False}]})
        creative.save_annotation(self.conn, "late-brand", late)

    def tearDown(self):
        self.conn.close()

    def test_brand_timing_split(self):
        out = qa.answer(self.conn, "Does early brand appearance win?")
        self.assertIn("Brand within the first 3.0s", out["answer"])
        self.assertIn("Brand after 3.0s", out["answer"])

    def test_logo_timing_split(self):
        out = qa.answer(self.conn, "Which logo timing wins?")
        self.assertIn("Logo within the first 3.0s", out["answer"])

    def test_audio_timing_split(self):
        out = qa.answer(self.conn, "When is the brand mentioned in audio?")
        self.assertIn("Audible brand mention within the first 3.0s",
                      out["answer"])


class DateRangeTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_range_matches_window_only(self):
        scope = Scope({"date_from": ["2026-08-01"],
                       "date_to": ["2026-08-03"]})
        cols = [c[0] for c in self.conn.execute(
            "SELECT * FROM ads LIMIT 0").description]
        rows = [dict(zip(cols, v)) for v in self.conn.execute(
            "SELECT * FROM ads").fetchall()]
        kept = sorted(r["ad_name"] for r in rows if scope.match(r))
        self.assertEqual(kept, ["A1", "A2", "B1"])

    def test_undated_rows_out_of_range(self):
        scope = Scope({"date_from": ["2026-08-01"]})
        self.assertFalse(scope.match({"date": ""}))
        self.assertTrue(scope.match({"date": "2026-09-01"}))

    def test_bad_day_rejected(self):
        with self.assertRaises(ValueError):
            Scope({"date_from": ["08/01/2026"]}).normalized()
        with self.assertRaises(ValueError):
            Scope({"date_to": ["2026-13-01"]}).normalized()

    def test_reversed_window_rejected(self):
        with self.assertRaises(ValueError):
            benchmarks.compare_periods(self.conn, "2026-08-05",
                                       "2026-08-01", "2026-08-04",
                                       "2026-08-07")

    def test_periods_split_and_delta(self):
        got = benchmarks.compare_periods(
            self.conn, "2026-08-01", "2026-08-03",
            "2026-08-04", "2026-08-07")
        self.assertEqual(got["a"]["n_ads"], 3)
        self.assertEqual(got["a"]["kpis"]["spend"], 350.0)
        self.assertEqual(got["b"]["n_ads"], 4)
        self.assertEqual(got["b"]["kpis"]["spend"], 210.0)
        self.assertEqual(got["delta"]["spend"], -140.0)

    def test_periods_route(self):
        got = _fetch("/api/compare/periods?a_from=2026-08-01"
                     "&a_to=2026-08-03&b_from=2026-08-04&b_to=2026-08-07")
        self.assertEqual(got["a"]["kpis"]["spend"], 350.0)
        self.assertEqual(got["delta"]["spend"], -140.0)
        self.assertEqual(got["scope"], "All data")

    def test_periods_route_rejects_reversed(self):
        r = _test_port().get(
            "/api/compare/periods?a_from=2026-08-05&a_to=2026-08-01"
            "&b_from=2026-08-04&b_to=2026-08-07")
        self.assertEqual(r.status_code, 409)
        self.assertIn("error", r.json())

    def test_describe_shows_range(self):
        scope = Scope({"market": ["Spain"],
                       "date_from": ["2026-08-01"],
                       "date_to": ["2026-08-03"]})
        self.assertIn("2026-08-01..2026-08-03", scope.describe())


class BriefsAndMarketsTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_briefs_are_specific_and_verified_aligned(self):
        extras = benchmarks._report_extras(self.conn, ["CampA", "CampB"],
                                           rank_by="cpa")
        recos = extras["recommendations"]
        self.assertEqual(len(recos),
                         len(extras["recommendations_verified"]))
        self.assertTrue(any(r.startswith("SCALE —") for r in recos))
        self.assertTrue(any(r.startswith("STOP —") for r in recos))
        self.assertTrue(any("Brief more 'demo_open' hooks" in r
                            for r in recos))
        self.assertTrue(any("branded formats lead on CPA" in r
                            for r in recos))
        self.assertTrue(any("Brief <=" in r for r in recos))
        self.assertTrue(any("CTA at ~25.0s" in r for r in recos))
        self.assertTrue(any("MARKET — Spain leads" in r for r in recos))
        self.assertTrue(any("MARKET — France underperforms" in r
                            for r in recos))

    def test_markets_table_and_section(self):
        extras = benchmarks._report_extras(self.conn, ["CampA", "CampB"],
                                           rank_by="cpa")
        by_name = {m["market"]: m for m in extras["markets"]}
        self.assertEqual(by_name["Spain"]["spend"], 150.0)
        self.assertTrue(by_name["Spain"]["qualified"])
        # France clears both thresholds (310 spend, 5 conversions).
        self.assertTrue(by_name["France"]["qualified"])
        self.assertEqual(by_name["France"]["spend"], 310.0)
        rep = benchmarks.build_report(self.conn, ["CampA", "CampB"],
                                      ["cpa"], None, "one-pager")
        self.assertIn("## Markets (scoped)", rep["markdown"])
        # CampA alone leaves France thin ($30 spend): noted, not ranked.
        thin = benchmarks._report_extras(self.conn, ["CampA"],
                                         rank_by="cpa")
        self.assertTrue(any("too early to judge" in r
                            for r in thin["recommendations"]))


class RetentionCurveTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_acc_db()

    def tearDown(self):
        self.conn.close()

    def test_curve_points_and_markers(self):
        got = retention.curve(self.conn, "shared-creative")
        self.assertEqual([(p["t"], p["p"]) for p in got["points"][:3]],
                         [(0.0, 100.0), (3.0, 98.0), (6.0, 95.0)])
        self.assertEqual(got["points"][-1], {"t": 30.0, "p": 72.0})
        markers = got["markers"]
        self.assertEqual(markers["product_s"], 6.2)
        self.assertEqual(markers["brand_s"], 0.5)
        self.assertEqual(markers["cta_s"], 25.0)
        self.assertEqual(markers["hook"], {"start_s": 0.0, "end_s": 3.0})

    def test_curve_needs_annotation_and_curve(self):
        with self.assertRaises(ValueError):
            retention.curve(self.conn, "zero-creative")
        with self.assertRaises(ValueError):
            retention.curve(self.conn, "no-such-creative")

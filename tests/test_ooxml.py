"""True PPTX/XLSX tests (stdlib only).

Builders must emit valid ZIP packages whose every XML part parses;
the reader must roundtrip builder output and handle hand-made
workbooks (shared/inline/numeric/boolean cells). Report integration
proves /api/report formats carry decodable Office bytes.
"""

import base64
import os
import sqlite3
import sys
import unittest
import zipfile
from io import BytesIO
from xml.dom import minidom

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import benchmarks, ingest, ooxml, schema


def parts(blob):
    zf = zipfile.ZipFile(BytesIO(blob))
    try:
        return {n: zf.read(n) for n in zf.namelist()}
    finally:
        zf.close()


def assert_all_xml_valid(test, files):
    for name, data in files.items():
        if name.endswith((".xml", ".rels")):
            try:
                minidom.parseString(data)
            except Exception as e:
                test.fail("%s is not valid XML: %s" % (name, e))


class PptxTest(unittest.TestCase):
    def test_builds_valid_package(self):
        blob = ooxml.build_pptx("T", [
            {"title": "Slide One", "bullets": ["a: 1", "b: 2 <>&"]},
            {"title": "Why X leads", "bullets": ["because data"]}])
        self.assertTrue(blob.startswith(b"PK"))
        files = parts(blob)
        self.assertIn("ppt/presentation.xml", files)
        self.assertIn("ppt/slides/slide1.xml", files)
        self.assertIn("ppt/slides/slide2.xml", files)
        self.assertIn("ppt/theme/theme1.xml", files)
        assert_all_xml_valid(self, files)
        self.assertIn(b"Slide One", files["ppt/slides/slide1.xml"])
        self.assertIn(b"00C7B2", files["ppt/slides/slide1.xml"])
        # hostile text is escaped, never raw markup
        self.assertNotIn(b"2 <>&", files["ppt/slides/slide1.xml"])
        self.assertIn(b"2 &lt;&gt;&amp;", files["ppt/slides/slide1.xml"])

    def test_needs_slides(self):
        with self.assertRaises(ValueError):
            ooxml.build_pptx("T", [])


class XlsxTest(unittest.TestCase):
    def test_builds_valid_workbook(self):
        blob = ooxml.build_xlsx([
            {"name": "Campaigns", "header": ["campaign", "spend", "ctr"],
             "rows": [["Alpha", 120.5, 0.0125], ["Beta & Co", 0, 0]]}])
        self.assertTrue(blob.startswith(b"PK"))
        files = parts(blob)
        self.assertIn("xl/workbook.xml", files)
        self.assertIn("xl/worksheets/sheet1.xml", files)
        assert_all_xml_valid(self, files)
        self.assertIn(b"00C7B2", files["xl/styles.xml"])
        self.assertIn(b'horizontal="center"', files["xl/styles.xml"])
        self.assertIn(b"FFC6EFCE", files["xl/styles.xml"])
        self.assertIn(b"FFFFC7CE", files["xl/styles.xml"])
        self.assertIn(b"<cols>", files["xl/worksheets/sheet1.xml"])

    def test_roundtrip(self):
        rows = [["Alpha", 120.5, 0.0125, True], ["Beta", 0, 0.0, False]]
        blob = ooxml.build_xlsx([
            {"name": "Campaigns", "header": ["campaign", "spend", "ctr", "flag"],
             "rows": rows}])
        files = parts(blob)
        assert_all_xml_valid(self, files)
        sheet1 = files["xl/worksheets/sheet1.xml"]
        self.assertIn(b't="b" s="2"', sheet1)
        self.assertIn(b't="b" s="3"', sheet1)
        got = ooxml.parse_xlsx(blob)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["campaign"], "Alpha")
        self.assertAlmostEqual(got[0]["spend"], 120.5)
        self.assertAlmostEqual(got[0]["ctr"], 0.0125)
        self.assertIs(got[0]["flag"], True)
        self.assertEqual(got[1]["campaign"], "Beta")

    def test_rejects_bad_zip(self):
        with self.assertRaises(ValueError):
            ooxml.parse_xlsx(b"definitely not a zip")

    def test_empty_sheet(self):
        blob = ooxml.build_xlsx([{"name": "E", "header": ["a"], "rows": []}])
        self.assertEqual(ooxml.parse_xlsx(blob), [])

    def test_needs_sheets(self):
        with self.assertRaises(ValueError):
            ooxml.build_xlsx([])


class ReportBinaryTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        schema.init_db(self.conn)
        rows, _ = ingest.parse_csv_report(
            "campaign,spend,impressions,clicks,conversions,revenue\n"
            "Alpha,100,10000,200,10,250\n"
            "Beta,300,30000,300,30,750\n", "meta", "test")
        ingest.insert_rows(self.conn, rows)

    def tearDown(self):
        self.conn.close()

    def test_pptx_report_carries_office_bytes(self):
        rep = benchmarks.build_report(self.conn, None, ["cpa", "ctr"], None,
                                      "pptx")
        self.assertEqual(rep["format"], "pptx")
        self.assertEqual(rep["filename"], "campaign-report.pptx")
        blob = base64.b64decode(rep["pptx_b64"])
        files = parts(blob)
        assert_all_xml_valid(self, files)
        self.assertIn(b"Alpha", files["ppt/slides/slide2.xml"])

    def test_xlsx_report_roundtrips(self):
        rep = benchmarks.build_report(self.conn, None, ["cpa", "ctr"], None,
                                      "xlsx")
        self.assertEqual(rep["format"], "xlsx")
        rows = ooxml.parse_xlsx(base64.b64decode(rep["xlsx_b64"]))
        self.assertEqual([r["Campaign"] for r in rows], ["Alpha", "Beta"])
        self.assertIn("CPA", rows[0])

    def test_bad_format_still_rejected(self):
        with self.assertRaises(ValueError):
            benchmarks.build_report(self.conn, None, ["cpa"], None, "keynote")


class XlsxIngestTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        schema.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def _workbook(self):
        return ooxml.build_xlsx([{
            "name": "Export",
            "header": ["Campaign", "Amount Spent", "Impressions", "Link Clicks",
                       "Results", "Video Views", "Ad Name"],
            "rows": [["Gamma", 50.0, 5000, 100, 5, 1500, "g1"],
                     ["Gamma", "oops", 5000, 100, 5, 1500, "g2"]]}])

    def test_xlsx_parses_with_aliases_and_quarantine(self):
        rows, quarantined = ingest.parse_xlsx_report(
            self._workbook(), "meta", "test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["campaign"], "Gamma")
        self.assertEqual(rows[0]["spend"], 50.0)
        self.assertEqual(rows[0]["creative_key"], "g1")
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0]["source_row"], 3)

    def test_xlsx_inserts(self):
        from ci_backend import actions as server
        rows, _ = ingest.parse_xlsx_report(self._workbook(), "tiktok", "test")
        self.assertEqual(ingest.insert_rows(self.conn, rows), 1)
        out = server.apply_action(
            self.conn,
            "ingest", {"platform": "meta", "source": "upload",
                       "xlsx_b64": base64.b64encode(self._workbook()).decode()},
            None)
        self.assertEqual(out["inserted"], 1)
        self.assertEqual(out["quarantined_count"], 1)

    def test_xlsx_rejects_garbage(self):
        with self.assertRaises(ValueError):
            ingest.parse_xlsx_report(b"nope", "meta", "test")
        with self.assertRaises(ValueError):
            ingest.parse_xlsx_report(
                ooxml.build_xlsx([{"name": "E", "header": ["a"], "rows": []}]),
                "meta", "test")


if __name__ == "__main__":
    unittest.main()

"""QI124/QI126: XLSX text identity and catalogue worksheet order.

Synthetic workbooks only. Text cells must stay text on export, and
worksheet selection must follow workbook catalogue order via
relationships, never ZIP filename sorting.
"""

import io
import os
import re
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import ooxml


def _rewrite_workbook(blob, transform):
    src = zipfile.ZipFile(io.BytesIO(bytes(blob)))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "xl/workbook.xml":
                data = transform(data.decode("utf-8")).encode("utf-8")
            dst.writestr(name, data)
    src.close()
    return out.getvalue()


class XlsxTextIdentityTests(unittest.TestCase):
    def test_numeric_looking_text_stays_text_round_trip(self):
        blob = ooxml.build_xlsx([{
            "name": "Data",
            "header": ["creative_key", "code", "long_id", "spend",
                       "ctr", "flag"],
            "rows": [["000123", "02", "12345678901234567890", 123,
                      1.5, True]],
        }])
        got = ooxml.parse_xlsx(blob)
        self.assertEqual(len(got), 1)
        row = got[0]
        self.assertEqual(row["creative_key"], "000123")
        self.assertEqual(row["code"], "02")
        self.assertEqual(row["long_id"], "12345678901234567890")
        self.assertEqual(row["spend"], 123)
        self.assertIsInstance(row["spend"], int)
        self.assertAlmostEqual(row["ctr"], 1.5)
        self.assertIs(row["flag"], True)

    def test_decimal_numbers_remain_numeric(self):
        blob = ooxml.build_xlsx([{
            "name": "Data", "header": ["label", "value"],
            "rows": [["spend", 120.5], ["count", 7]],
        }])
        got = ooxml.parse_xlsx(blob)
        self.assertAlmostEqual(got[0]["value"], 120.5)
        self.assertEqual(got[1]["value"], 7)


class XlsxCatalogueOrderTests(unittest.TestCase):
    def _marked_workbook(self, count):
        return ooxml.build_xlsx([{
            "name": "S%d" % i, "header": ["marker"],
            "rows": [["sheet-%d" % i]],
        } for i in range(count)])

    def test_second_of_twelve_sheets_is_catalogue_second(self):
        blob = self._marked_workbook(12)
        self.assertEqual(ooxml.sheet_names(blob),
                         ["S%d" % i for i in range(12)])
        got = ooxml.parse_xlsx(blob, sheet=1)
        self.assertEqual(got, [{"marker": "sheet-1"}])

    def test_reordered_catalogue_keeps_names_and_data_aligned(self):
        blob = self._marked_workbook(3)

        def swap_first_two(book):
            tags = re.findall(r"<sheet\b[^>]*>", book)
            self.assertEqual(len(tags), 3)
            return book.replace(tags[0] + tags[1], tags[1] + tags[0], 1)

        reordered = _rewrite_workbook(blob, swap_first_two)
        self.assertEqual(ooxml.sheet_names(reordered), ["S1", "S0", "S2"])
        self.assertEqual(ooxml.parse_xlsx(reordered, sheet=0),
                         [{"marker": "sheet-1"}])
        self.assertEqual(ooxml.parse_xlsx(reordered, sheet=1),
                         [{"marker": "sheet-0"}])

    def test_out_of_range_sheet_index_is_rejected(self):
        blob = self._marked_workbook(2)
        with self.assertRaises(ValueError):
            ooxml.parse_xlsx(blob, sheet=2)

    def test_missing_relationships_are_a_clear_error(self):
        blob = self._marked_workbook(2)
        src = zipfile.ZipFile(io.BytesIO(bytes(blob)))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for name in src.namelist():
                if name != "xl/_rels/workbook.xml.rels":
                    dst.writestr(name, src.read(name))
        src.close()
        with self.assertRaises(ValueError):
            ooxml.parse_xlsx(out.getvalue(), sheet=0)


if __name__ == "__main__":
    unittest.main()

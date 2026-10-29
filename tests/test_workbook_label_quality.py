"""Test the permitted workbook cell-formatting fragment on synthetic rows.

No report workflow, application imports, XLSX writer or archive is executed.
The fragment and its pure formatting helpers are extracted from actual source.
"""

import ast
import copy
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Backend" / "creative_intel" / "benchmarks.py"
tree = ast.parse(SOURCE.read_text())
helpers = {"_display_slug", "_display_label"}
constants = {"_HEADER_ACRONYMS", "_DISPLAY_PLATFORMS", "_SLUG_FIELDS"}
selected = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in helpers:
        assert not node.decorator_list and not node.args.defaults
        selected.append(node)
    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in constants:
            literal = node.value
            if isinstance(literal, ast.Call):
                assert isinstance(literal.func, ast.Name) and literal.func.id == "frozenset"
                assert len(literal.args) == 1 and not literal.keywords
                literal = literal.args[0]
            ast.literal_eval(literal)
            selected.append(node)
assert len(selected) == len(helpers | constants)

# Select only the existing index-selection assignment and following formatting
# loop. Do not compile or call the mixed enclosing build_report function.
selections = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
              and any(isinstance(v, ast.Name) and v.id == "_SLUG_FIELDS"
                      for v in ast.walk(n.value))]
assert len(selections) == 1
selection = selections[0]
containers = [n.body for n in ast.walk(tree)
              if isinstance(getattr(n, "body", None), list) and selection in n.body]
assert len(containers) == 1
body = containers[0]
format_loop = body[body.index(selection) + 1]
assert isinstance(format_loop, ast.For)
assert isinstance(format_loop.target, ast.Name) and format_loop.target.id == "row"
assert {n.func.id for n in ast.walk(format_loop) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)} == {"len", "_display_slug"}
assert not any(isinstance(n, (ast.Import, ast.ImportFrom, ast.Attribute))
               for n in ast.walk(format_loop))
formatting = ast.FunctionDef(
    name="format_entry", args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="entry")],
                                           kwonlyargs=[], kw_defaults=[], defaults=[]),
    body=[selection, format_loop], decorator_list=[],
)
selected.append(formatting)
namespace = {"re": re}
exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])),
             str(SOURCE), "exec"), namespace)


def formatted(header, rows):
    entry = copy.deepcopy({"header": header, "rows": rows})
    namespace["format_entry"](entry)
    return entry


class WorkbookLabelQualityTests(unittest.TestCase):
    def test_creative_identifiers_keep_punctuation_and_case_distinct(self):
        values = ["ad_001", "ad-001", "Ad_001", "AD_001"]
        rows = [[value, value] for value in values]
        self.assertEqual(formatted(["creative", "creative_key"], rows)["rows"], rows)

    def test_creative_identifiers_keep_spacing_and_unicode(self):
        values = ["  ad_001  ", "ad  one", "żółć_01", "creative\tname"]
        rows = [[value] for value in values]
        self.assertEqual(formatted(["creative_key"], rows)["rows"], rows)

    def test_free_form_cta_preserves_timing_punctuation_and_whitespace(self):
        values = ["0-3s: buy_now", "  Buy  NOW — click_here!  ", "first\nsecond", ""]
        rows = [[value] for value in values]
        self.assertEqual(formatted(["cta"], rows)["rows"], rows)

    def test_categorical_codes_still_receive_readable_labels(self):
        header = ["role", "hook", "hook_type", "hook_modality", "format",
                  "creator_vs_branded", "edit_style", "structure", "source"]
        row = ["best_in_scope", "hook-a", "demo_open", "voice-over", "short_video",
               "creator_led", "fast_cut", "before_after", "meta"]
        expected = ["Best In Scope", "Hook A", "Demo Open", "Voice Over", "Short Video",
                    "Creator Led", "Fast Cut", "Before After", "Meta"]
        self.assertEqual(formatted(header, [row])["rows"], [expected])

    def test_platform_brand_casing_and_acronyms_are_preserved(self):
        rows = [["tiktok", "cta_test"], ["META", "roas_focus"]]
        self.assertEqual(formatted(["platform", "hook_type"], rows)["rows"],
                         [["TikTok", "CTA Test"], ["Meta", "ROAS Focus"]])

    def test_non_string_values_pass_through_the_formatting_stage(self):
        rows = [[None, 0, False, 1.5]]
        self.assertEqual(formatted(["creative", "cta", "platform", "hook_type"], rows)["rows"],
                         rows)

    def test_short_rows_and_extra_cells_are_not_corrupted(self):
        rows = [["ad_001"], ["ad-001", "demo_open", "extra_value"]]
        self.assertEqual(formatted(["creative_key", "hook_type"], rows)["rows"],
                         [["ad_001"], ["ad-001", "Demo Open", "extra_value"]])

    def test_unknown_fields_remain_exact_without_categorical_guessing(self):
        rows = [["free_form-name", "  untouched  text  "]]
        self.assertEqual(formatted(["custom_id", "description"], rows)["rows"], rows)

    def test_empty_rows_and_field_order_preserve_header_contract(self):
        header = ["cta", "creative_key", "platform", "creative"]
        self.assertEqual(formatted(header, []), {"header": header, "rows": []})
        row = ["buy_now", "ad_001", "tiktok", "Ad-001"]
        self.assertEqual(formatted(header, [row]),
                         {"header": header, "rows": [["buy_now", "ad_001", "TikTok", "Ad-001"]]})

    def test_header_labels_remain_humanized_separately_from_cell_values(self):
        label = namespace["_display_label"]
        self.assertEqual([label(key) for key in ["creative_key", "cta", "duration_s", "cpa"]],
                         ["Creative Key", "CTA", "Duration (s)", "CPA"])


if __name__ == "__main__":
    unittest.main()

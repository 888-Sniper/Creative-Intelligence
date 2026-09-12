"""Foap Analyst blank-workbook tests (spec sections 17 + 19).

Structure (Input at A6, 200 rows, context in M-T, seven sheets) plus
formula agreement: every Metrics/Benchmarks formula is extracted from
the generated .xlsx XML, evaluated by a small in-test evaluator over
a labelled fixture, and compared against the shared backend engine.
Labelled example values (1.18 s / 1.02 s) are fixtures only.
"""

import html
import io
import json
import os
import re
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import analyst_metrics as metrics
from creative_intel import analyst_workbook as wb

# ----------------------------------------------------------------
# .xlsx parsing helpers (values + formulas, no new dependencies)


def _sheets_xml(blob):
    zf = zipfile.ZipFile(io.BytesIO(bytes(blob)))
    try:
        shared = []
        try:
            sst = zf.read("xl/sharedStrings.xml").decode("utf-8")
            shared = [html.unescape(re.sub(r"<[^>]+>", "", m))
                      for m in re.findall(r"<si>(.*?)</si>", sst, re.S)]
        except KeyError:
            pass
        names = re.findall(r'<sheet name="([^"]+)"',
                           zf.read("xl/workbook.xml").decode("utf-8"))
        out = {}
        for i, name in enumerate(names, 1):
            xml = zf.read("xl/worksheets/sheet%d.xml" % i).decode("utf-8")
            out[name] = (xml, shared)
    finally:
        zf.close()
    return out


def _cell_grid(xml, shared):
    """(ref, kind, payload): kind is 'formula', 'num' or 'text'."""
    cells = {}
    # Self-closing branch first: otherwise `<c r="B4"/>` would match the
    # open-cell branch with attrs swallowing `/><c r="C4" ...`.
    for m in re.finditer(r'<c r="([A-Z]+\d+)"[^>]*/>|'
                         r'<c r="([A-Z]+\d+)"([^>]*)>(.*?)</c>', xml, re.S):
        if m.group(1):
            ref, attrs, inner = m.group(1), "", None
        else:
            ref, attrs, inner = m.group(2), m.group(3), m.group(4)
        if inner is not None:
            fm = re.search(r"<f>(.*?)</f>", inner, re.S)
            if fm:
                cells[ref] = ("formula", html.unescape(fm.group(1)))
                continue
            text = re.sub(r"<[^>]+>", "", inner or "").strip()
            if 't="s"' in attrs:
                try:
                    cells[ref] = ("text", shared[int(text)])
                except (ValueError, IndexError):
                    cells[ref] = ("text", "")
            elif text == "":
                cells[ref] = ("text", "")
            else:
                try:
                    cells[ref] = ("num", float(text))
                except ValueError:
                    cells[ref] = ("text", text)
        else:
            cells[ref] = ("text", "")
    return cells


def _colkey(ref):
    return (re.match(r"[A-Z]+", ref).group(0),
            int(re.match(r"[A-Z]+(\d+)", ref).group(1)))


# ----------------------------------------------------------------
# Minimal evaluator for the formula subset the workbook emits:
# IF/OR/AND/SUM/AVERAGE/MEDIAN/COUNT, comparisons, +-*/, &,
# cross-sheet refs, ranges, numbers and "strings".


class _Tok:
    def __init__(self, kind, value):
        self.kind = kind
        self.value = value


def _strip_absolute(expr):
    """Drop $ absolute markers outside string literals."""
    out, i, quoted = [], 0, False
    while i < len(expr):
        ch = expr[i]
        if ch == '"':
            quoted = not quoted
            out.append(ch)
        elif ch == "$" and not quoted:
            pass
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _tokenize(expr):
    expr = _strip_absolute(expr)
    tokens, i = [], 0
    while i < len(expr):
        ch = expr[i]
        if ch.isspace():
            i += 1
        elif ch == '"':
            j = expr.index('"', i + 1)
            tokens.append(_Tok("str", expr[i + 1:j]))
            i = j + 1
        elif ch.isdigit() or (ch == "." and i + 1 < len(expr)
                              and expr[i + 1].isdigit()):
            m = re.match(r"\d+(\.\d+)?", expr[i:])
            tokens.append(_Tok("num", float(m.group(0))))
            i += m.end()
        elif ch.isalpha() or ch in ("_", "!"):
            m = re.match(r"[A-Za-z_][A-Za-z0-9_.]*(![A-Za-z]+[0-9]+)?"
                         r"(:[A-Za-z]+[0-9]+)?", expr[i:])
            word = m.group(0)
            tokens.append(_Tok("name", word))
            i += len(word)
        elif expr.startswith("<>", i) or expr.startswith("<=", i) \
                or expr.startswith(">=", i):
            tokens.append(_Tok("op", expr[i:i + 2]))
            i += 2
        elif ch in "=<>+-*/&(),":
            tokens.append(_Tok("op" if ch in "=<>+-*/&" else ch, ch))
            i += 1
        else:
            raise ValueError("bad char %r in %r" % (ch, expr))
    return tokens


class Evaluator:
    def __init__(self, sheets):
        # sheets: name -> {ref: ("formula"|"num"|"text", payload)}
        self.sheets = sheets
        self._stack = []

    def cell(self, sheet, ref):
        key = (sheet, ref)
        if key in self._stack:
            raise ValueError("circular ref %s!%s" % (sheet, ref))
        kind, payload = self.sheets[sheet].get(ref, ("text", ""))
        if kind == "formula":
            self._stack.append(key)
            try:
                return self.eval(payload, sheet)
            finally:
                self._stack.pop()
        return payload

    def range_vals(self, sheet, span):
        first, last = span.split(":")
        fc, fr = _colkey(first)
        lc, lr = _colkey(last)
        assert fc == lc
        return [self.cell(sheet, "%s%d" % (fc, r))
                for r in range(fr, lr + 1)]

    def eval(self, expr, sheet):
        # Re-entrant: cell refs evaluate nested formulas mid-parse.
        saved = (self.__dict__.get("_tokens"),
                 self.__dict__.get("_pos"),
                 self.__dict__.get("_sheet"))
        self._tokens = _tokenize(expr)
        self._pos = 0
        self._sheet = sheet
        try:
            value = self._parse_cmp()
            if self._pos != len(self._tokens):
                raise ValueError("trailing tokens in %r" % expr)
            return value
        finally:
            self._tokens, self._pos, self._sheet = saved

    def _peek(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) \
            else None

    def _next(self):
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _parse_cmp(self):
        left = self._parse_add()
        tok = self._peek()
        if tok and tok.kind == "op" and tok.value in (
                "=", "<>", "<", ">", "<=", ">="):
            self._next()
            right = self._parse_add()
            return self._compare(tok.value, left, right)
        if tok and tok.kind == "op" and tok.value == "&":
            parts = [left]
            while self._peek() and self._peek().kind == "op" \
                    and self._peek().value == "&":
                self._next()
                parts.append(self._parse_add())
            return "".join(self._text(p) for p in parts)
        return left

    @staticmethod
    def _num(value):
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _text(value):
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _compare(self, op, left, right):
        if isinstance(left, _Err) or isinstance(right, _Err):
            return False
        ln, rn = self._num(left), self._num(right)
        if ln is not None and rn is not None:
            left, right = ln, rn
        else:
            left, right = self._text(left), self._text(right)
        return {"=": left == right, "<>": left != right,
                "<": left < right, ">": left > right,
                "<=": left <= right, ">=": left >= right}[op]

    def _arith(self, op, left, right):
        # Excel-like: arithmetic over text yields an error that only the
        # taken IF branch discards, so guards can be evaluated eagerly.
        if isinstance(left, _Err) or isinstance(right, _Err):
            return _Err()
        left, right = self._num(left), self._num(right)
        if left is None or right is None:
            return _Err()
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if right == 0:
            return _Err()
        return left / right

    def _parse_add(self):
        value = self._parse_mul()
        while self._peek() and self._peek().kind == "op" \
                and self._peek().value in ("+", "-"):
            op = self._next().value
            value = self._arith(op, value, self._parse_mul())
        return value

    def _parse_mul(self):
        value = self._parse_atom()
        while self._peek() and self._peek().kind == "op" \
                and self._peek().value in ("*", "/"):
            op = self._next().value
            value = self._arith(op, value, self._parse_atom())
        return value

    def _parse_atom(self):
        tok = self._next()
        if tok.kind == "num":
            return tok.value
        if tok.kind == "str":
            return tok.value
        if tok.kind == "(":
            value = self._parse_cmp()
            assert self._next().kind == ")"
            return value
        if tok.kind == "name":
            name = tok.value.upper()
            if self._peek() and self._peek().kind == "(":
                self._next()
                args = []
                if not (self._peek() and self._peek().kind == ")"):
                    args.append(self._parse_cmp())
                    while self._peek() and self._peek().kind == ",":
                        self._next()
                        args.append(self._parse_cmp())
                assert self._next().kind == ")"
                return self._call(name, args)
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*!"
                             r"[A-Za-z]+[0-9]+:[A-Za-z]+[0-9]+",
                             tok.value):
                sheet, span = tok.value.split("!")
                return _Range(sheet.strip("'"), span)
            if "!" in tok.value:
                sheet, ref = tok.value.split("!")
                return self.cell(sheet.strip("'"), ref)
            if re.fullmatch(r"[A-Z]+[0-9]+", tok.value):
                return self.cell(self._sheet, tok.value)
            if ":" in tok.value:
                raise ValueError("bare range %r" % tok.value)
            raise ValueError("unknown name %r" % tok.value)
        raise ValueError("unexpected %r" % (tok.value,))

    def _call(self, name, args):
        if name == "IF":
            cond, then, otherwise = args
            return then if self._truthy(cond) else otherwise
        if name == "OR":
            return any(self._truthy(a) for a in args)
        if name == "AND":
            return all(self._truthy(a) for a in args)
        if name == "SUMIFS":
            sum_range = args[0]
            assert isinstance(sum_range, _Range)
            pairs = list(zip(args[1::2], args[2::2]))
            sum_vals = self.range_vals(sum_range.sheet, sum_range.span)
            crit_lists = []
            for rng, _crit in pairs:
                assert isinstance(rng, _Range)
                crit_lists.append(self.range_vals(rng.sheet, rng.span))
            total = 0.0
            for i, value in enumerate(sum_vals):
                kept = all(self._match_crit(crit, vals[i])
                           for (_, crit), vals in zip(pairs, crit_lists))
                num = self._num(value)
                if kept and num is not None:
                    total += num
            return total
        if name in ("SUM", "AVERAGE", "MEDIAN", "COUNT"):
            values = []
            for arg in args:
                if isinstance(arg, _Range):
                    values.extend(
                        self.range_vals(arg.sheet, arg.span))
                else:
                    values.append(arg)
            nums = [v for v in (self._num(x) for x in values)
                    if v is not None]
            if name == "SUM":
                return sum(nums)
            if name == "COUNT":
                return len(nums)
            if not nums:
                raise ValueError("%s of empty set" % name)
            if name == "AVERAGE":
                return sum(nums) / len(nums)
            ordered = sorted(nums)
            mid = len(ordered) // 2
            if len(ordered) % 2:
                return ordered[mid]
            return (ordered[mid - 1] + ordered[mid]) / 2.0
        raise ValueError("unsupported function %s" % name)

    @staticmethod
    def _match_crit(crit, value):
        # Only the "<>" / "=" criteria the workbook emits.
        blank = (value == "" or value is None)
        if isinstance(value, bool):
            blank = False
        if crit == "<>":
            return not blank
        if crit == "=":
            return blank
        raise ValueError("unsupported criterion %r" % (crit,))

    @staticmethod
    def _truthy(value):
        if isinstance(value, _Err):
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value).strip().upper()
        if text in ("", "FALSE"):
            return False
        if text == "TRUE":
            return True
        return True


class _Range:
    def __init__(self, sheet, span):
        self.sheet = sheet
        self.span = span


class _Err:
    """Arithmetic over text (e.g. an "n/a" guard branch not taken)."""


# ----------------------------------------------------------------
# Fixtures. Labelled example values (1.18 s / 1.02 s) are synthetic
# fixtures only — never real Foap performance.


def eng_row(key, values, missing=()):
    base = {"platform": "tiktok", "source": "upload", "campaign": "C",
            "adset": "", "ad_name": key, "creative_key": key,
            "watch_time_basis": "starts", "currency": "PLN",
            "missing_json": json.dumps(sorted(set(missing)))}
    base.update(values)
    return base


INPUT_FIELDS = [field for _, field, _ in wb.INPUT_COLUMNS]


def split_fixture(values):
    """workbook prefill dict + engine row pair for one creative."""
    present = {k: v for k, v in values.items() if v is not None}
    missing = [f for f in INPUT_FIELDS
               if f not in present and f not in ("creative_key",)]
    row = eng_row(values.get("creative_key", "?"), dict(present),
                  missing=[m for m in missing
                           if m in ("impressions", "reach", "video_starts",
                                    "views_2s", "views_3s", "views_25",
                                    "views_50", "views_75", "views_100",
                                    "watch_time_total_s", "spend")])
    return present, row


FIXTURE = [
    {"creative_key": "HOOK_OK", "impressions": 10000, "reach": 8000,
     "video_starts": 4000, "views_2s": 3000, "views_3s": 2500,
     "views_25": 1500, "views_50": 900, "views_75": 600,
     "views_100": 500, "watch_time_total_s": 4720.0, "spend": 100.0,
     "duration_s": 20},
    {"creative_key": "HOOK_WEAK", "impressions": 10000, "reach": 8000,
     "video_starts": 3500, "views_2s": 800, "views_3s": 700,
     "views_25": 400, "views_50": 250, "views_75": 150,
     "views_100": 100, "watch_time_total_s": 3570.0, "spend": 100.0,
     "duration_s": 20},
    # Labelled watch-time example: 1.18 s vs 1.02 s (fixture only).
    {"creative_key": "AWT_HIGH", "impressions": 5000, "reach": 4000,
     "video_starts": 100, "views_2s": 60, "views_3s": 55,
     "views_25": 40, "views_50": 30, "views_75": 20,
     "views_100": 15, "watch_time_total_s": 118.0, "spend": 20.0,
     "duration_s": 15},
    {"creative_key": "AWT_LOW", "impressions": 5000, "reach": 4000,
     "video_starts": 100, "views_2s": 55, "views_3s": 50,
     "views_25": 38, "views_50": 28, "views_75": 18,
     "views_100": 12, "watch_time_total_s": 102.0, "spend": 20.0,
     "duration_s": 15},
    # Missing 2s views: must stay unavailable, never substituted.
    {"creative_key": "NO_2S", "impressions": 9000, "reach": 7000,
     "video_starts": 3000, "views_2s": None, "views_3s": 2000,
     "views_25": 1200, "views_50": 700, "views_75": 400,
     "views_100": 300, "watch_time_total_s": 3000.0, "spend": 50.0,
     "duration_s": 18},
    # Short video: 25% lands before 3 s, hold is incompatible.
    {"creative_key": "SHORT_6S", "impressions": 6000, "reach": 5000,
     "video_starts": 2500, "views_2s": 1500, "views_3s": 1200,
     "views_25": 1100, "views_50": 600, "views_75": 300,
     "views_100": 200, "watch_time_total_s": 2500.0, "spend": 30.0,
     "duration_s": 6},
]


def build_fixture():
    prefill = []
    engine_rows = []
    for values in FIXTURE:
        present, row = split_fixture(values)
        prefill.append((values["creative_key"], present))
        engine_rows.append(row)
    blob = wb.build_blank_workbook(prefill=prefill)
    sheets = {name: _cell_grid(xml, shared)
              for name, (xml, shared) in _sheets_xml(blob).items()}
    return Evaluator(sheets), engine_rows, blob


# metric column -> engine callable over a single-row list
def _engine_metric(col):
    if col == "B":
        return metrics.hook_rate_2s
    if col == "C":
        return metrics.hook_rate_3s
    if col == "E":
        return lambda rows: metrics.pooled_ratio(
            rows, "quartile_25_impr", "views_25", "impressions")
    if col == "F":
        return lambda rows: metrics.pooled_ratio(
            rows, "quartile_50_impr", "views_50", "impressions")
    if col == "G":
        return lambda rows: metrics.pooled_ratio(
            rows, "vtr", "views_100", "impressions")
    if col == "J":
        return metrics.cpm
    if col == "K":
        return metrics.cpcv
    if col == "L":
        return metrics.cost_per_1000_reached
    raise AssertionError(col)


def _agree(test, evaluated, engine_value):
    """Workbook formula value agrees with the backend engine result."""
    if engine_value is None:
        test.assertIsInstance(evaluated, str)
        test.assertTrue(evaluated.startswith("n/a"),
                        "expected n/a marker, got %r" % (evaluated,))
    else:
        test.assertIsInstance(evaluated, float,
                              "expected number, got %r" % (evaluated,))
        test.assertAlmostEqual(evaluated, engine_value, places=6)


class WorkbookStructureTest(unittest.TestCase):
    def test_seven_sheets_input_at_a6_200_rows_context_m_to_t(self):
        blob = wb.build_blank_workbook()
        sheets = _sheets_xml(blob)
        self.assertEqual(
            list(sheets),
            ["Input", "Metrics", "Benchmarks", "Hypotheses",
             "Creative Summary", "Test Plan", "Definitions"])
        cells = _cell_grid(*sheets["Input"])
        headers = {cells["%s5" % col][1]
                   for col, _, _ in wb.INPUT_COLUMNS}
        self.assertIn("Creative", headers)
        # Required metric inputs in A-L, optional context in M-T.
        letters = [col for col, _, _ in wb.INPUT_COLUMNS]
        self.assertEqual(letters[:12],
                         list("ABCDEFGHIJKL"))
        self.assertEqual(letters[12:], list("MNOPQRST"))
        for row in (6, 205):
            for col in "AT":
                self.assertIn("%s%d" % (col, row), cells)
        self.assertNotIn("A206", cells)
        # Metrics rows mirror Input rows with real formulas.
        metrics_cells = _cell_grid(*sheets["Metrics"])
        self.assertEqual(metrics_cells["B6"][0], "formula")
        self.assertIn("Input!E6", metrics_cells["B6"][1])
        self.assertIn("Input!B6", metrics_cells["B6"][1])

    def test_cover_sheet_records_configuration(self):
        blob = wb.build_blank_workbook(cover={
            "name": "Q1 Report", "description": "Quarterly read.",
            "modules": ["summary", "breakdown"],
            "kpis": ["Impressions", "ROAS"]})
        sheets = _sheets_xml(blob)
        self.assertEqual(
            list(sheets),
            ["Workbook", "Input", "Metrics", "Benchmarks", "Hypotheses",
             "Creative Summary", "Test Plan", "Definitions"])
        cells = _cell_grid(*sheets["Workbook"])
        text = " ".join(v for _, v in cells.values())
        self.assertIn("Q1 Report", text)
        self.assertIn("summary, breakdown", text)
        self.assertIn("Impressions, ROAS", text)

    def test_no_cover_without_configuration(self):
        blob = wb.build_blank_workbook()
        sheets = _sheets_xml(blob)
        self.assertNotIn("Workbook", list(sheets))

    def test_definitions_come_from_shared_registry(self):
        blob = wb.build_blank_workbook()
        sheets = _sheets_xml(blob)
        cells = _cell_grid(*sheets["Definitions"])
        ids = {cells[ref][1] for ref in cells
               if _colkey(ref)[0] == "A" and _colkey(ref)[1] > 5
               and cells[ref][1]}
        for mid in ("hook_rate_2s_impr", "hook_rate_3s_impr", "vtr",
                    "cpm", "cpcv"):
            self.assertIn(mid, ids)


class WorkbookAgreementTest(unittest.TestCase):
    def test_metric_formulas_match_engine(self):
        ev, rows, _blob = build_fixture()
        by_key = {r["creative_key"]: r for r in rows}
        for i, values in enumerate(FIXTURE):
            excel_row = wb.FIRST_DATA_ROW + i
            row = [by_key[values["creative_key"]]]
            for col in "BCEFGJKL":
                evaluated = ev.cell("Metrics", "%s%d" % (col, excel_row))
                _agree(self, evaluated,
                       _engine_metric(col)(row)["value"])

    def test_awt_and_pct_match_engine(self):
        ev, rows, _blob = build_fixture()
        by_key = {r["creative_key"]: r for r in rows}
        for i, values in enumerate(FIXTURE):
            excel_row = wb.FIRST_DATA_ROW + i
            row = [by_key[values["creative_key"]]]
            awt, pct = metrics.awt_per_view(
                row, durations={values["creative_key"]:
                                values["duration_s"]})
            _agree(self, ev.cell("Metrics", "H%d" % excel_row),
                   awt["value"])
            _agree(self, ev.cell("Metrics", "I%d" % excel_row),
                   pct["value"])

    def test_labelled_watch_time_difference(self):
        # Labelled fixture: 1.18 s vs 1.02 s -> +0.16 s, about +15.7%.
        ev, _rows, _blob = build_fixture()
        high = ev.cell("Metrics", "H8")
        low = ev.cell("Metrics", "H9")
        self.assertAlmostEqual(high, 1.18, places=6)
        self.assertAlmostEqual(low, 1.02, places=6)
        self.assertAlmostEqual(high - low, 0.16, places=6)
        self.assertAlmostEqual((high - low) / low * 100, 15.7, places=1)

    def test_missing_2s_never_substituted(self):
        ev, _rows, _blob = build_fixture()
        # NO_2S is the 5th fixture row -> Excel row 10.
        self.assertEqual(ev.cell("Metrics", "B10"), "n/a")
        # ...while its 3s hook still computes (no cross-substitution).
        self.assertAlmostEqual(ev.cell("Metrics", "C10"),
                               2000 / 9000 * 100, places=6)

    def test_short_video_hold_incompatible(self):
        ev, _rows, _blob = build_fixture()
        # SHORT_6S is the 6th fixture row -> Excel row 11.
        hold = ev.cell("Metrics", "D11")
        self.assertIsInstance(hold, str)
        self.assertIn("before 3s", hold)
        # Long videos keep a numeric hold.
        self.assertIsInstance(ev.cell("Metrics", "D6"), float)

    def test_benchmarks_match_engine_aggregates(self):
        ev, rows, _blob = build_fixture()
        pooled = metrics.hook_rate_2s(rows)["value"]
        mean = metrics.mean_of_rates(
            rows, "hook_rate_2s_impr", "views_2s", "impressions")["value"]
        median = metrics.median_of_rates(
            rows, "hook_rate_2s_impr", "views_2s", "impressions")["value"]
        self.assertAlmostEqual(ev.cell("Benchmarks", "B6"), pooled,
                               places=6)
        self.assertAlmostEqual(ev.cell("Benchmarks", "C6"), mean,
                               places=6)
        self.assertAlmostEqual(ev.cell("Benchmarks", "D6"), median,
                               places=6)
        # n counts only measurable creatives (NO_2S excluded).
        self.assertEqual(ev.cell("Benchmarks", "E6"), 5)

    def test_benchmark_rows_read_own_metric_column(self):
        sheet = wb._benchmarks_sheet()["rows"]
        data = sheet[5:]  # past the 4-row title block + header
        by_label = {row[0]: row for row in data}
        # Cost rows must average their own Metrics columns, never
        # the AWT % column (I).
        for label, col in (("CPM", "J"), ("CPCV", "K"),
                           ("Cost per 1000 reached", "L")):
            mean = by_label[label][2]["formula"]
            self.assertIn("Metrics!%s" % col, mean)
            self.assertNotIn("Metrics!I", mean)
        # The two AWT rows share mid None but read different columns.
        self.assertIn("Metrics!H", by_label["AWT s"][2]["formula"])
        self.assertIn("Metrics!I",
                      by_label["AWT % of duration"][2]["formula"])

    def test_hypotheses_are_labelled_candidates(self):
        ev, _rows, _blob = build_fixture()
        weak = ev.cell("Hypotheses", "B7")
        self.assertIn("Candidate:", weak)
        ok = ev.cell("Hypotheses", "B6")
        self.assertNotIn("LOW", ok)
        # No data -> explicit insufficient-data marker, never a verdict.
        self.assertEqual(ev.cell("Hypotheses", "B12"), "insufficient data")


if __name__ == "__main__":
    unittest.main()

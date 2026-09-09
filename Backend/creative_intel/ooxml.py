"""True Office Open XML builders + reader, stdlib only.

OOXML is ZIP + XML, so real .pptx / .xlsx files need nothing beyond
zipfile: no third-party dependency, no network, no secrets.

- build_pptx(title, slides) -> bytes  (title + KPI bullet slides,
  Foap-teal title runs, opens in PowerPoint/LibreOffice/Keynote)
- build_xlsx(sheets) -> bytes         (teal header row, shared strings)
- parse_xlsx(blob) -> [dict]          (first row = headers; shared,
  inline, numeric, boolean cells; empty rows skipped)
"""

import re
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

NAMES = {
    "content_types": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
    "office_doc": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "core": "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
    "app": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
    "slide": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
    "master": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
    "layout": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
    "theme": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
    "sheet": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "styles": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
    "strings": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings",
}

DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
PRESENTATION = "http://schemas.openxmlformats.org/presentationml/2006/main"
SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

EMU_IN = 914400
TEAL = "00C7B2"


def _zip(files):
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files:
            data = text.encode("utf-8") if isinstance(text, str) else text
            zf.writestr(name, data)
    return buf.getvalue()


def _rels(*targets):
    items = "".join(
        '<Relationship Id="rId%d" Type="%s" Target="%s"/>' % (i + 1, kind, path)
        for i, (kind, path) in enumerate(targets))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s">%s</Relationships>'
            % (NAMES["rels"], items))


def _core_props(title):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<dc:title>%s</dc:title>"
            "<dc:creator>Foap Creative Intelligence</dc:creator>"
            "</cp:coreProperties>" % escape(title))


def _app_props(slides=1):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>Foap Creative Intelligence</Application>"
            '<Slides>%d</Slides></Properties>' % slides)


# ---------------------------------------------------------------- PPTX ---

_PPTX_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="%s">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
    '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
    '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
    '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    "%s</Types>")

_PPTX_THEME = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<a:theme xmlns:a="%s" name="Foap">'
    "<a:themeElements><a:clrScheme name=\"Foap\">"
    '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
    '<a:dk1><a:srgbClr val="17211F"/></a:dk1>'
    '<a:lt2><a:srgbClr val="F2FCFB"/></a:lt2>'
    '<a:dk2><a:srgbClr val="5F6B69"/></a:dk2>'
    '<a:accent1><a:srgbClr val="00C7B2"/></a:accent1>'
    '<a:accent2><a:srgbClr val="008F7F"/></a:accent2>'
    '<a:accent3><a:srgbClr val="0E7C5B"/></a:accent3>'
    '<a:accent4><a:srgbClr val="8A6100"/></a:accent4>'
    '<a:accent5><a:srgbClr val="C0362C"/></a:accent5>'
    '<a:accent6><a:srgbClr val="E5E8E6"/></a:accent6>'
    '<a:hlink><a:srgbClr val="008F7F"/></a:hlink>'
    '<a:folHlink><a:srgbClr val="5F6B69"/></a:folHlink>'
    "</a:clrScheme>"
    '<a:fmtScheme name="Foap">'
    "<a:fillStyleLst>"
    '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="lt1"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="dk1"/></a:solidFill>'
    "</a:fillStyleLst>"
    "<a:lnStyleLst>"
    '<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln w="12700"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    '<a:ln w="19050"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    "</a:lnStyleLst>"
    "<a:effectStyleLst>"
    "<a:effectStyle><a:effectLst/></a:effectStyle>"
    "<a:effectStyle><a:effectLst/></a:effectStyle>"
    "<a:effectStyle><a:effectLst/></a:effectStyle>"
    "</a:effectStyleLst>"
    "<a:bgFillStyleLst>"
    '<a:solidFill><a:schemeClr val="lt1"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="lt2"/></a:solidFill>'
    '<a:solidFill><a:schemeClr val="dk1"/></a:solidFill>'
    "</a:bgFillStyleLst>"
    "</a:fmtScheme></a:themeElements></a:theme>" % DRAWING)

_PPTX_MASTER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldMaster xmlns:a="%s" xmlns:p="%s" xmlns:r="%s">'
    "<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val=\"FFFFFF\"/></a:solidFill></p:bgPr></p:bg>"
    "<p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>"
    "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
    "</p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
    '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
    "<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz=\"4400\" b=\"1\"><a:solidFill><a:srgbClr val=\"17211F\"/></a:solidFill></a:defRPr></a:lvl1pPr></p:titleStyle>"
    "<p:bodyStyle><a:lvl1pPr><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:bodyStyle>"
    "<p:otherStyle><a:lvl1pPr><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:otherStyle></p:txStyles>"
    "</p:sldMaster>" % (DRAWING, PRESENTATION, NAMES["rels"].replace(
        "/package/2006/relationships",
        "/officeDocument/2006/relationships")))

_PPTX_LAYOUT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<p:sldLayout xmlns:a="%s" xmlns:p="%s" xmlns:r="%s" type="titleAndContent" preserve="1">'
    "<p:cSld name=\"Title and Content\"><p:spTree>"
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
    "</p:spTree></p:cSld>"
    '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:clrMapOvr>'
    "</p:sldLayout>" % (DRAWING, PRESENTATION, NAMES["rels"].replace(
        "/package/2006/relationships",
        "/officeDocument/2006/relationships")))


def _pptx_paragraphs(title, bullets, title_size=3200):
    out = ['<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/>'
           "<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
           '<p:spPr><a:xfrm><a:off x="457200" y="274320"/>'
           '<a:ext cx="11267640" cy="1000000"/></a:xfrm></p:spPr>'
           "<p:txBody><a:bodyPr/><a:lstStyle/>"
           '<a:p><a:r><a:rPr lang="en-US" b="1" sz="%d">'
           '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
           "</a:rPr><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>"
           % (title_size, TEAL, escape(title))]
    body = ['<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content"/>'
            "<p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
            '<p:spPr><a:xfrm><a:off x="457200" y="1473200"/>'
            '<a:ext cx="11267640" cy="4500000"/></a:xfrm></p:spPr>'
            "<p:txBody><a:bodyPr/><a:lstStyle/>"]
    for bullet in bullets:
        body.append('<a:p><a:pPr marL="228600" indent="-228600">'
                    '<a:buChar char="•"/></a:pPr>'
                    '<a:r><a:rPr lang="en-US" sz="1800">'
                    '<a:solidFill><a:srgbClr val="17211F"/></a:solidFill>'
                    "</a:rPr><a:t>%s</a:t></a:r></a:p>" % escape(str(bullet)))
    body.append("</p:txBody></p:sp>")
    out.extend(body)
    return "".join(out)


def _pptx_slide(title, bullets):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:a="%s" xmlns:p="%s" xmlns:r="%s">'
            "<p:cSld><p:spTree>"
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            "<p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/>"
            "<a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>"
            "%s</p:spTree></p:cSld>"
            '<p:clrMapOvr><a:overrideClrMapping bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" '
            'accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" '
            'accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
            "</p:clrMapOvr></p:sld>"
            % (DRAWING, PRESENTATION,
               NAMES["rels"].replace("/package/2006/relationships",
                                     "/officeDocument/2006/relationships"),
               _pptx_paragraphs(title, bullets)))


def build_pptx(title, slides):
    """slides: [{"title": str, "bullets": [str]}] -> .pptx bytes."""
    if not slides:
        raise ValueError("pptx needs at least one slide")
    files = []
    slide_overrides = "".join(
        '<Override PartName="/ppt/slides/slide%d.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' % (i + 1)
        for i in range(len(slides)))
    files.append(("[Content_Types].xml", _PPTX_TYPES % (NAMES["content_types"],
                                                       slide_overrides)))
    files.append(("_rels/.rels", _rels(
        (NAMES["office_doc"], "ppt/presentation.xml"),
        (NAMES["core"], "docProps/core.xml"),
        (NAMES["app"], "docProps/app.xml"))))
    sld_ids = "".join(
        '<p:sldId id="%d" r:id="rId%d"/>' % (256 + i, i + 2)
        for i in range(len(slides)))
    files.append(("ppt/presentation.xml",
                  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  '<p:presentation xmlns:a="%s" xmlns:p="%s" xmlns:r="%s">'
                  '<p:sldMasterIdLst><p:sldMasterId r:id="rId1"/></p:sldMasterIdLst>'
                  "<p:sldIdLst>%s</p:sldIdLst>"
                  '<p:sldSz cx="12192000" cy="6858000" type="screen16x9"/>'
                  "</p:presentation>" % (DRAWING, PRESENTATION,
                                          NAMES["rels"].replace(
                                              "/package/2006/relationships",
                                              "/officeDocument/2006/relationships"),
                                          sld_ids)))
    pres_rels = [(NAMES["master"], "slideMasters/slideMaster1.xml")]
    pres_rels += [(NAMES["slide"], "slides/slide%d.xml" % (i + 1))
                  for i in range(len(slides))]
    files.append(("ppt/_rels/presentation.xml.rels", _rels(*pres_rels)))
    files.append(("ppt/slideMasters/slideMaster1.xml", _PPTX_MASTER))
    files.append(("ppt/slideMasters/_rels/slideMaster1.xml.rels", _rels(
        (NAMES["layout"], "../slideLayouts/slideLayout1.xml"),
        (NAMES["theme"], "../theme/theme1.xml"))))
    files.append(("ppt/slideLayouts/slideLayout1.xml", _PPTX_LAYOUT))
    files.append(("ppt/slideLayouts/_rels/slideLayout1.xml.rels", _rels(
        (NAMES["master"], "../slideMasters/slideMaster1.xml"))))
    files.append(("ppt/theme/theme1.xml", _PPTX_THEME))
    for i, slide in enumerate(slides):
        files.append(("ppt/slides/slide%d.xml" % (i + 1),
                      _pptx_slide(str(slide.get("title", "")),
                                  [str(b) for b in slide.get("bullets", [])])))
        files.append(("ppt/slides/_rels/slide%d.xml.rels" % (i + 1), _rels(
            (NAMES["layout"], "../slideLayouts/slideLayout1.xml"))))
    files.append(("docProps/core.xml", _core_props(title)))
    files.append(("docProps/app.xml", _app_props(len(slides))))
    return _zip(files)


# ---------------------------------------------------------------- XLSX ---

_XLSX_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="%s">'
    "<fonts count=\"2\">"
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
    "</fonts>"
    '<fills count="3">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FF00C7B2"/><bgColor indexed="64"/></patternFill></fill>'
    "</fills>"
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="2">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"/>'
    "</cellXfs></styleSheet>" % SPREADSHEET)


def _col_letters(index):
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _split_ref(ref):
    match = re.match(r"([A-Za-z]+)([0-9]+)$", ref or "")
    if not match:
        return None, None
    col = 0
    for ch in match.group(1).upper():
        col = col * 26 + (ord(ch) - 64)
    return col - 1, int(match.group(2)) - 1


class _Strings:
    def __init__(self):
        self.index = {}
        self.items = []

    def idx(self, text):
        if text not in self.index:
            self.index[text] = len(self.items)
            self.items.append(text)
        return self.index[text]

    def xml(self):
        inner = "".join(
            "<si><t xml:space=\"preserve\">%s</t></si>" % escape(t)
            for t in self.items)
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>'
                % (SPREADSHEET, len(self.items), len(self.items), inner))


def _xlsx_cell(ref, value, strings, header=False):
    style = ' s="1"' if header else ""
    if value is None:
        return '<c r="%s"%s/>' % (ref, style)
    if isinstance(value, bool):
        return '<c r="%s" t="b"%s><v>%d</v></c>' % (ref, style, int(value))
    if isinstance(value, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, style, repr(value))
    return '<c r="%s" t="s"%s><v>%d</v></c>' % (
        ref, style, strings.idx(str(value)))


def build_xlsx(sheets):
    """sheets: [{"name": str, "header": [str], "rows": [[values]]}] -> bytes."""
    if not sheets:
        raise ValueError("xlsx needs at least one sheet")
    strings = _Strings()
    sheet_files = []
    for pos, sheet in enumerate(sheets):
        header = [str(h) for h in sheet.get("header", [])]
        rows = sheet.get("rows", [])
        width = max([len(header)] + [len(r) for r in rows] or [0])
        xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               '<worksheet xmlns="%s"><sheetData>' % SPREADSHEET]
        for r, values in enumerate([header] + [list(map(str_or_num, r_))
                                               for r_ in rows]):
            xml.append('<row r="%d">' % (r + 1))
            for c in range(width):
                val = values[c] if c < len(values) else None
                xml.append(_xlsx_cell("%s%d" % (_col_letters(c), r + 1),
                                      val, strings, header=(r == 0)))
            xml.append("</row>")
        xml.append("</sheetData></worksheet>")
        sheet_files.append(("xl/worksheets/sheet%d.xml" % (pos + 1),
                            "".join(xml)))
    names = "".join(
        '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (
            escape(str(s.get("name", "Sheet%d" % (i + 1)))[:31] or "Sheet",
                   {'"': "&quot;"}), i + 1, i + 1)
        for i, s in enumerate(sheets))
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="%s" xmlns:r="%s">'
                "<sheets>%s</sheets></workbook>"
                % (SPREADSHEET,
                   NAMES["rels"].replace("/package/2006/relationships",
                                         "/officeDocument/2006/relationships"),
                   names))
    wb_rels = [(NAMES["sheet"], "worksheets/sheet%d.xml" % (i + 1))
               for i in range(len(sheets))]
    wb_rels += [(NAMES["styles"], "styles.xml"),
                (NAMES["strings"], "sharedStrings.xml")]
    sheet_types = "".join(
        '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
        for i in range(len(sheets)))
    files = [
        ("[Content_Types].xml",
         '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Types xmlns="%s">'
         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
         '<Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
         "%s"
         '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
         '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
         '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
         '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
         "</Types>" % (NAMES["content_types"], sheet_types)),
        ("_rels/.rels", _rels(
            (NAMES["office_doc"], "xl/workbook.xml"),
            (NAMES["core"], "docProps/core.xml"),
            (NAMES["app"], "docProps/app.xml"))),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", _rels(*wb_rels)),
        ("xl/styles.xml", _XLSX_STYLES),
        ("xl/sharedStrings.xml", strings.xml()),
        ("docProps/core.xml", _core_props("Foap Creative Intelligence report")),
        ("docProps/app.xml", _app_props()),
    ] + sheet_files
    return _zip(files)


def str_or_num(value):
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return value
    return value


def _text_of(node_xml):
    return re.sub(r"<[^>]+>", "", node_xml or "")


def parse_xlsx(blob):
    """Parse the first worksheet: first row -> headers, rest -> dicts."""
    try:
        zf = zipfile.ZipFile(BytesIO(bytes(blob)))
    except zipfile.BadZipFile:
        raise ValueError("not an xlsx file (bad zip)")
    try:
        shared = []
        try:
            sst = zf.read("xl/sharedStrings.xml").decode("utf-8")
            shared = [_text_of(m) for m in
                      re.findall(r"<si>(.*?)</si>", sst, re.S)]
        except KeyError:
            pass
        names = [n for n in zf.namelist()
                 if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
        if not names:
            raise ValueError("xlsx has no worksheets")
        sheet = zf.read(sorted(names)[0]).decode("utf-8")
    finally:
        zf.close()
    grid = {}
    for row_xml in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        for cell in re.findall(r"<c\b(.*?)</c>|<c\b(.*?)/>", row_xml, re.S):
            if cell[0] and ">" in cell[0]:
                # Group spans attributes + inner XML: split at first ">".
                attrs, inner = cell[0].split(">", 1)
                inner = inner or None
            else:
                attrs, inner = cell[0] or cell[1], None
            ref = re.search(r'r="([^"]+)"', attrs)
            typ = re.search(r't="([^"]+)"', attrs)
            if not ref:
                continue
            col, row = _split_ref(ref.group(1))
            if col is None:
                continue
            kind = typ.group(1) if typ else ""
            if inner is None:
                value = None
            elif kind == "s":
                try:
                    value = shared[int(_text_of(inner).strip())]
                except (ValueError, IndexError):
                    value = None
            elif kind == "inlineStr":
                value = _text_of(inner)
            elif kind == "b":
                value = _text_of(inner).strip() == "1"
            elif kind == "str":
                value = _text_of(inner)
            else:
                value = str_or_num(_text_of(inner).strip())
            grid.setdefault(row, {})[col] = value
    if not grid:
        return []
    widths = max(max(cells) + 1 for cells in grid.values())
    headers = [str(grid[0].get(c, "col%d" % (c + 1))) for c in range(widths)]
    out = []
    for r in sorted(k for k in grid if k > 0):
        cells = grid[r]
        if all(v is None or v == "" for v in cells.values()):
            continue
        out.append({headers[c]: cells.get(c) for c in range(widths)})
    return out

"""Deterministic sample thumbnail art for creatives (SVG).

Synthetic creatives (demo seeds, imports without attached media) have no
uploaded artwork, so cards would otherwise show plain colour blocks.
This module renders a designed SVG per creative — name, platform,
duration and hook composed over a key-derived scene — served through an
authenticated endpoint. Real uploaded media keeps precedence wherever
it is rendered; the CSS gradient remains the fallback when no image is
genuinely available (unknown creative, backend error).
"""

import hashlib

WIDTH, HEIGHT = 480, 360


def _escape(text: str) -> str:
    """Minimal XML text escaper (no xml import: nothing is parsed here,
    so there is no XXE surface; keeps the dependency tree unchanged)."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def hue_for(key: str) -> int:
    return int(hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:8],
               16) % 360


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def sample_svg(key: str, name: str = "", platform: str = "",
               duration_s=None, hook: str = "") -> str:
    """Render sample thumbnail SVG for one creative (pure function)."""
    hue = hue_for(key or name or "creative")
    hue2 = (hue + 48) % 360
    title = _escape(_short(name or key, 30))
    plat = _escape(_short(str(platform or "").upper(), 12))
    secs = None
    try:
        secs = float(duration_s) if duration_s is not None else None
    except (TypeError, ValueError):
        secs = None
    meta_bits = [b for b in (
        plat,
        _escape(_short(str(hook or "").replace("_", " "), 18)) if hook else "",
        ("%ds" % round(secs)) if secs else "",
    ) if b]
    meta = " · ".join(meta_bits)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d"'
        ' viewBox="0 0 %d %d" role="img">'
        "<defs><linearGradient id=\"g\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">"
        "<stop offset=\"0\" stop-color=\"hsl(%d,45%%,34%%)\"/>"
        "<stop offset=\"1\" stop-color=\"hsl(%d,52%%,16%%)\"/>"
        "</linearGradient></defs>"
        '<rect width="%d" height="%d" fill="url(#g)"/>'
        '<circle cx="400" cy="60" r="130" fill="#7FE3D2" opacity="0.16"/>'
        '<circle cx="60" cy="320" r="150" fill="#7FE3D2" opacity="0.12"/>'
        '<circle cx="400" cy="60" r="80" fill="#BFF3EA" opacity="0.14"/>'
        '<g opacity="0.9"><circle cx="240" cy="150" r="34" fill="#ffffff"'
        ' opacity="0.92"/><path d="M232 132 L262 150 L232 168 Z"'
        ' fill="hsl(%d,50%%,26%%)"/></g>'
        '<text x="240" y="222" text-anchor="middle" font-family="system-ui,'
        'sans-serif" font-size="30" font-weight="700" fill="#ffffff">%s</text>'
        '<text x="240" y="252" text-anchor="middle" font-family="system-ui,'
        'sans-serif" font-size="17" fill="#CDEEE8">%s</text>'
        '<rect x="352" y="20" width="104" height="30" rx="15"'
        ' fill="#000000" opacity="0.35"/>'
        '<text x="404" y="41" text-anchor="middle" font-family="system-ui,'
        'sans-serif" font-size="15" font-weight="700" letter-spacing="2"'
        ' fill="#ffffff">SAMPLE</text>'
        "</svg>"
        % (WIDTH, HEIGHT, WIDTH, HEIGHT, hue, hue2, WIDTH, HEIGHT,
           hue, title, meta))


def uploaded_image_url(conn, store, key: str):
    """First uploaded image's /media/<id> URL, or None.

    Uploaded media takes precedence over generated art; a database row
    whose file is missing does not count (genuine fallback then).
    Raises ValueError for malformed keys.
    """
    import os as _os

    from . import media as _media

    _media.check_key(key)
    _media.ensure_schema(conn)
    conn.row_factory = None
    row = conn.execute(
        "SELECT id, stored_name FROM media WHERE creative_key=?"
        " AND mime LIKE 'image/%' ORDER BY id LIMIT 1", (key,)).fetchone()
    if not row:
        return None
    if _os.path.basename(row[1]) != row[1]:
        return None
    if not _os.path.isfile(_os.path.join(store or "", row[1])):
        return None
    return "/media/%s" % row[0]


def for_creative(conn, key: str):
    """Sample SVG for a stored creative, or None when unknown.

    Raises ValueError for malformed keys (same grain as media keys).
    """
    from . import media as _media

    _media.check_key(key)
    conn.row_factory = None
    row = conn.execute(
        "SELECT name, platform, duration_s FROM creatives"
        " WHERE creative_key=?", (key,)).fetchone()
    if not row:
        return None
    name, platform, duration_s = row[0], row[1], row[2]
    hook = ""
    try:
        from creative_intel import creative as _creative_mod
        _ann = _creative_mod.annotation_for_key(conn, key)
        if isinstance(_ann, dict):
            hook = str(_ann.get("hook_type") or "")
    except ValueError:
        hook = ""
    return sample_svg(key, name=name, platform=platform,
                      duration_s=duration_s, hook=hook)

"""Creative sample thumbnails: deterministic SVG art, auth-gated.

Creatives without uploaded media get designed sample art (name,
platform, duration, hook) instead of plain colour blocks; unknown
creatives 404 so cards keep the gradient fallback.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

import pytest  # noqa: E402
from creative_intel import thumbnails
from test_admin_demo_seed import _demo_client


@pytest.fixture(autouse=True)
def _isolated_media_dir(tmp_path, monkeypatch):
    # Seeded demo artwork must never land in the repo Data/ tree.
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR",
                       str(tmp_path / "media"))


def test_sample_svg_is_deterministic_and_escaped():
    a = thumbnails.sample_svg("k1", name="Hello <World>", platform="tiktok",
                              duration_s=18, hook="demo_open")
    assert thumbnails.sample_svg("k1", name="Hello <World>",
                                 platform="tiktok", duration_s=18,
                                 hook="demo_open") == a
    assert "<World>" not in a
    assert "Hello" in a and "SAMPLE" in a and "<svg" in a
    assert thumbnails.sample_svg("k1", name="A") != thumbnails.sample_svg(
        "k2", name="A")


def test_thumbnail_endpoint_serves_seeded_art(tmp_path):
    # Demo seeding stores a distinct uploaded image per creative, so
    # the thumbnail prefers real media over the generated fallback.
    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    r = http.get("/api/creatives/demo-glowskin-01/thumbnail",
                 headers=headers, follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["location"].startswith("/media/")
    r = http.get(r.headers["location"], headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_thumbnail_falls_back_to_sample_svg(tmp_path):
    # Genuine fallback only: a creative with no uploaded image keeps
    # the deterministic labelled SVG (name, platform, SAMPLE).
    import sqlite3 as _sqlite3

    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    conn = _sqlite3.connect(str(tmp_path / "seed.db"))
    try:
        conn.execute("DELETE FROM media WHERE creative_key=?",
                     ("demo-glowskin-01",))
        conn.commit()
    finally:
        conn.close()
    r = http.get("/api/creatives/demo-glowskin-01/thumbnail",
                 headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "Glowing Skin Made Easy" in r.text
    assert "SAMPLE" in r.text


def test_thumbnail_unknown_key_404s(tmp_path):
    http, headers = _demo_client(tmp_path)
    r = http.get("/api/creatives/no-such-creative/thumbnail", headers=headers)
    assert r.status_code == 404, r.text


def test_thumbnail_requires_auth(tmp_path):
    http, _headers = _demo_client(tmp_path)
    r = http.get("/api/creatives/demo-glowskin-01/thumbnail")
    assert r.status_code in (401, 403), r.text


def test_thumbnail_prefers_uploaded_media(tmp_path, monkeypatch):
    import base64 as _b64

    from creative_intel import media as _media

    store = str(tmp_path / "media")
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", store)
    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    png = _b64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
    import sqlite3 as _sqlite3

    db = str(tmp_path / "seed.db")
    conn = _sqlite3.connect(db)
    try:
        # Seeding already stored art; clear it so this upload is the
        # only image row (stable oldest-first ordering keeps serving
        # deterministic when several uploads exist).
        conn.execute("DELETE FROM media WHERE creative_key=?",
                     ("demo-glowskin-01",))
        conn.commit()
        rec = _media.save_media(conn, store, "demo-glowskin-01", "shot.png",
                                png)
    finally:
        conn.close()
    r = http.get("/api/creatives/demo-glowskin-01/thumbnail",
                 headers=headers, follow_redirects=False)
    assert r.status_code == 302, r.text
    assert r.headers["location"] == "/media/%s" % rec["id"]
    # Follow explicitly (the test client drops per-request headers on
    # redirect): the uploaded bytes serve through the media route.
    r = http.get(r.headers["location"], headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/png")

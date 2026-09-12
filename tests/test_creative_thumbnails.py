"""Creative sample thumbnails: deterministic SVG art, auth-gated.

Creatives without uploaded media get designed sample art (name,
platform, duration, hook) instead of plain colour blocks; unknown
creatives 404 so cards keep the gradient fallback.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import thumbnails
from test_admin_demo_seed import _demo_client


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


def test_thumbnail_endpoint_serves_demo_art(tmp_path):
    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    r = http.get("/api/creatives/demo-glowskin-01/thumbnail", headers=headers)
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

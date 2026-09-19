"""Jev decision client: request shape, failure modes, env key.

Live network is never touched here (see the synthetic probe run
during integration); urlopen is stubbed throughout.
"""

import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import jev  # noqa: E402


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _fake_urlopen(payload):
    def _run(request, timeout=None):
        _run.seen = {"url": request.full_url,
                     "auth": request.get_header("Authorization"),
                     "body": json.loads(request.data.decode("utf-8"))}
        return _Response(json.dumps(payload).encode("utf-8"))
    _run.seen = {}
    return _run


def test_posts_state_questions_and_bearer(monkeypatch):
    fake = _fake_urlopen({"model": "jev-1.13.0",
                          "answers": {"ok": {"type": "noul",
                                             "noul": 0.9}}})
    monkeypatch.setattr(jev.urllib.request, "urlopen", fake)
    answers = jev.system_one(
        "synthetic probe",
        {"ok": {"type": "noul", "instructions": "fine?"}},
        api_key="k")
    assert answers == {"ok": {"type": "noul", "noul": 0.9}}
    assert fake.seen["url"] == jev.ENDPOINT
    assert fake.seen["auth"] == "Bearer k"
    assert fake.seen["body"]["model"] == "jev-latest"


def test_reads_key_from_environment(monkeypatch):
    fake = _fake_urlopen({"answers": {}})
    monkeypatch.setattr(jev.urllib.request, "urlopen", fake)
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-key")
    assert jev.system_one("s", {"q": {}}, api_key=None) == {}
    assert fake.seen["auth"] == "Bearer env-key"
    monkeypatch.delenv("TYPESAFE_API_KEY")
    with pytest.raises(jev.JevError, match="API key"):
        jev.system_one("s", {"q": {}}, api_key=None)


def test_rejects_empty_inputs():
    with pytest.raises(jev.JevError):
        jev.system_one("", {"q": {}}, api_key="k")
    with pytest.raises(jev.JevError):
        jev.system_one("s", {}, api_key="k")


def test_maps_auth_failure(monkeypatch):
    def _denied(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "denied",
                                     {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(jev.urllib.request, "urlopen", _denied)
    with pytest.raises(jev.JevError, match="HTTP 401"):
        jev.system_one("s", {"q": {}}, api_key="bad")


def test_maps_bad_payload(monkeypatch):
    monkeypatch.setattr(jev.urllib.request, "urlopen",
                        lambda request, timeout=None: _Response(b"nope"))
    with pytest.raises(jev.JevError, match="non-JSON"):
        jev.system_one("s", {"q": {}}, api_key="k")
    monkeypatch.setattr(jev.urllib.request, "urlopen",
                        lambda request, timeout=None: _Response(b"{}"))
    with pytest.raises(jev.JevError, match="no answers"):
        jev.system_one("s", {"q": {}}, api_key="k")

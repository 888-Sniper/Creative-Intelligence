"""Dependency-lock sync tests (pytest, stdlib only).

requirements.lock must stay a faithful hashed export of uv.lock so the
VM installs exactly the tree CI tested:
- every pin matches the uv.lock version,
- every locked package (minus the root project) is pinned,
- every pin carries sha256 hashes,
- every direct pyproject dependency is pinned,
- every install caller enforces --require-hashes.
"""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name):
    with open(os.path.join(ROOT, name)) as fh:
        return fh.read()


def _uv_packages():
    text = _read("uv.lock")
    return dict(re.findall(
        r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text))


def _req_pins():
    text = _read("requirements.lock")
    pins = {}
    current = None
    stanza_hashes = {}
    for line in text.splitlines():
        head = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s\\;]+)", line)
        if head:
            current = head.group(1).lower().replace("-", "_")
            pins[current] = head.group(2)
            stanza_hashes[current] = 0
        elif current is not None and "--hash=sha256:" in line:
            stanza_hashes[current] += 1
    return pins, stanza_hashes


def _norm(name):
    return name.lower().replace("-", "_").replace(".", "_")


def test_pins_match_uv_lock():
    uv = {_norm(n): v for n, v in _uv_packages().items()}
    pins, _hashes = _req_pins()
    assert pins, "requirements.lock has no pins"
    for name, version in pins.items():
        assert name in uv, "%s pinned but absent from uv.lock" % name
        assert uv[name] == version, \
            "%s: requirements.lock=%s uv.lock=%s" % (name, version, uv[name])


def test_every_locked_package_pinned():
    uv = {_norm(n) for n in _uv_packages()}
    # The root project itself is installed --no-deps from source.
    uv.discard(_norm("creative_intelligence"))
    pins, _hashes = _req_pins()
    assert uv <= set(pins), \
        "missing pins: %s" % sorted(uv - set(pins))


def test_every_pin_has_hashes():
    pins, hashes = _req_pins()
    bare = [n for n in pins if hashes.get(n, 0) == 0]
    assert not bare, "pins without hashes: %s" % bare


def test_direct_dependencies_pinned():
    text = _read("pyproject.toml")
    names = set()
    for section in re.findall(
            r"dependencies\s*=\s*\[(.*?)\]", text, re.S):
        for dep in re.findall(r'"([^"]+)"', section):
            base = re.split(r"[<>=!~\s\[]", dep.strip())[0]
            if base:
                names.add(_norm(base))
    pins, _hashes = _req_pins()
    assert names <= set(pins), \
        "unpinned direct deps: %s" % sorted(names - set(pins))


def test_installers_enforce_hashes():
    for name in ("deploy/oracle/install.sh",
                 "deploy/oracle/update.sh",
                 ".github/workflows/ci.yml"):
        text = _read(name)
        assert re.search(
            r"pip.*install --require-hashes -r .*requirements\.lock", text), \
            "%s must pip install requirements.lock with --require-hashes" % name

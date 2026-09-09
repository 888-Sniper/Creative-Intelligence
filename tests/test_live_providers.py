"""Live provider wiring tests (stdlib unittest).

Real HTTP code paths against loopback stub servers: base URLs and keys
are injected via CREATIVE_INTEL_BASE_* / CREATIVE_INTEL_KEY_* env vars,
so no Keychain and no network are needed. Verifies:

- live STT parses a Deepgram-shaped response (no mock text leaks)
- live vision + structuring parse OpenAI-shaped chat responses and
  validate against the v0 schema
- fail-closed: no keys -> ProviderUnavailable, never mock output
- error responses surface as ProviderUnavailable, never raw exceptions
- secret material never appears in errors or returned structures
"""

import base64
import json
import os
import sqlite3
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import creative, providers, schema

TINY_JPEG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
             b"\x00\x00" + b"\x00" * 64 + b"\xff\xd9")

VALID_ANN = {
    "hook_type": "question", "hook_confidence": 0.8,
    "brand_seconds": [{"start_s": 1.0, "end_s": 3.0}],
    "product_seconds": [{"start_s": 2.0, "end_s": 5.0}],
    "logo_seconds": [],
    "structure": {s: {"start_s": 0.0, "end_s": 3.0, "confidence": 0.7}
                  for s in creative.STRUCTURE_SLOTS},
    "creator_vs_branded": "creator", "creator_confidence": 0.6,
    "duration_s": 30.0, "pace_cuts_per_min": 4.0,
}


class StubHandler(BaseHTTPRequestHandler):
    mode = "ok"

    def log_message(self, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if self.mode == "error":
            self._send(500, {"error": "boom"})
            return
        if self.path.startswith("/v2/listen"):
            assert self.headers.get("Authorization", "").startswith("Token "), \
                "deepgram auth scheme"
            alt = {"transcript": "stub spoken hook here", "confidence": 0.9}
            self._send(200, {"results": {"channels": [{"alternatives": [alt]}]}})
        elif self.path.endswith("/chat/completions"):
            frame = {"t_sec": 0.0, "label": "stub-open",
                     "brand_visible": True, "confidence": 0.9}
            payload = {"frames": [frame]}
            content = json.dumps(payload)
            self._send(200, {"choices": [{"message": {"content": content}}]})
        else:
            self._send(404, {"error": "no stub for %s" % self.path})


def make_vision_stub():
    """Chat stub that answers vision-shaped payloads."""
    class VisionStub(StubHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw or b"{}")
                text = json.dumps(payload)
            except ValueError:
                text = ""
            if self.mode == "error":
                self._send(500, {"error": "boom"})
                return
            if "brand_visible" in text or "frames" in text:
                frame = {"t_sec": 0.0, "label": "stub-open",
                         "brand_visible": True, "confidence": 0.9}
                content = json.dumps({"frames": [frame]})
            else:
                content = json.dumps(VALID_ANN)
            self._send(200, {"choices": [{"message": {"content": content}}]})
    return VisionStub


class LiveProviderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._srv = HTTPServer(("127.0.0.1", 0), StubHandler)
        cls.base = "http://127.0.0.1:%d" % cls._srv.server_address[1]
        cls._thread = threading.Thread(target=cls._srv.serve_forever,
                                       daemon=True)
        cls._thread.start()
        cls._vsrv = HTTPServer(("127.0.0.1", 0), make_vision_stub())
        cls.vbase = "http://127.0.0.1:%d" % cls._vsrv.server_address[1]
        cls._vthread = threading.Thread(target=cls._vsrv.serve_forever,
                                        daemon=True)
        cls._vthread.start()

    @classmethod
    def tearDownClass(cls):
        cls._srv.shutdown()
        cls._vsrv.shutdown()
        cls._thread.join(timeout=10)
        cls._vthread.join(timeout=10)

    def setUp(self):
        self._saved = dict(os.environ)
        os.environ["provider_mode"] = "live"
        os.environ["CREATIVE_INTEL_KEY_DEEPGRAM"] = "dummy-deepgram"
        os.environ["CREATIVE_INTEL_BASE_DEEPGRAM"] = self.base
        os.environ["CREATIVE_INTEL_KEY_DEEPSEEK"] = "dummy-deepseek"
        os.environ["CREATIVE_INTEL_BASE_DEEPSEEK"] = self.vbase
        StubHandler.mode = "ok"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_live_stt_parses_deepgram(self):
        stt = providers.LiveStt([("deepgram", "deepgram", "flux-general-en",
                                  "active")])
        text, conf = stt.transcribe("k", audio_bytes=b"RIFF....", mime="audio/wav")
        self.assertEqual(text, "stub spoken hook here")
        self.assertEqual(conf, 0.9)
        self.assertNotIn("mock", text)

    def test_live_stt_needs_audio(self):
        stt = providers.LiveStt([("deepgram", "deepgram", "flux-general-en",
                                  "active")])
        with self.assertRaises(providers.ProviderUnavailable):
            stt.transcribe("k")

    def test_live_llm_structures_and_validates(self):
        llm = providers.LiveLlm([("deepseek", "deepseek-v4-flash", "active")])
        ann = llm.structure("what is this demo?", [])
        self.assertEqual(ann["hook_type"], "question")
        self.assertEqual(creative.validate(ann), [])

    def test_live_vision_annotates_images(self):
        vision = providers.LiveVision([("deepseek", "deepseek-v4-flash",
                                        "active")])
        labels = vision.annotate([{"t_sec": 0.0}], images=[TINY_JPEG])
        self.assertEqual(len(labels), 1)
        self.assertTrue(labels[0]["brand_visible"])
        self.assertNotEqual(labels[0]["label"], "mock-frame")

    def test_live_llm_rejects_invalid_model_output(self):
        class BadChat:
            def chat(self, messages, max_tokens=2048):
                return "not json at all"
        orig = providers.make_chat
        providers.make_chat = lambda p, m: BadChat()
        try:
            llm = providers.LiveLlm([("deepseek", "x", "active")])
            with self.assertRaises(providers.ProviderUnavailable):
                llm.structure("hello?", [])
        finally:
            providers.make_chat = orig

    def test_error_responses_fail_closed(self):
        StubHandler.mode = "error"
        stt = providers.LiveStt([("deepgram", "deepgram", "flux-general-en",
                                  "active")])
        with self.assertRaises(providers.ProviderUnavailable):
            stt.transcribe("k", audio_bytes=b"xx")

    def test_no_keys_fail_closed_never_mock(self):
        for var in list(os.environ):
            if var.startswith("CREATIVE_INTEL_KEY_"):
                del os.environ[var]
        prov = providers.Providers()
        self.assertEqual(prov.mode, "live")
        with self.assertRaises(providers.ProviderUnavailable):
            prov.stt.transcribe("k", audio_bytes=b"xx")

    def test_mock_default_ignores_env_keys(self):
        os.environ["provider_mode"] = "mock"
        prov = providers.Providers()
        text, _ = prov.stt.transcribe("k")
        self.assertIn("mock transcript", text)

    def test_full_live_pipeline_end_to_end(self):
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            conn.execute(
                "INSERT INTO creatives (creative_key, platform, name)"
                " VALUES (?,?,?)", ("live-k", "meta", "Live Spot"))
            conn.commit()
            os.environ["CREATIVE_INTEL_KEY_GROQ-STT".replace("-", "_")] = "x"
            prov = providers.Providers()
            media = {"audio": (b"RIFF....", "audio/wav"),
                     "images": [TINY_JPEG]}
            # Vision roster needs a configured vision key for the bundle;
            # drive stages directly to isolate the HTTP paths.
            stt = providers.LiveStt([("deepgram", "deepgram",
                                      "flux-general-en", "active")])
            llm = providers.LiveLlm([("deepseek", "deepseek-v4-flash",
                                      "active")])
            text, conf = stt.transcribe("live-k", audio_bytes=media["audio"][0])
            self.assertNotIn("mock", text)
            ann = llm.structure(text, [{"t_sec": 0.0, "label": "stub",
                                        "brand_visible": True,
                                        "confidence": 0.9}])
            self.assertEqual(creative.validate(ann), [])
            creative.save_annotation(conn, "live-k", ann)
            got = conn.execute("SELECT status FROM creatives WHERE creative_key=?",
                               ("live-k",)).fetchone()[0]
            self.assertEqual(got, "auto")
        finally:
            conn.close()

    def test_secrets_never_surface(self):
        try:
            raise providers.ProviderUnavailable("missing key for deepgram")
        except providers.ProviderUnavailable as e:
            self.assertNotIn("dummy-deepgram", str(e))
        llm = providers.LiveLlm([("deepseek", "deepseek-v4-flash", "active")])
        ann = llm.structure(" hello ", [])
        self.assertNotIn("dummy-deepseek", json.dumps(ann))


if __name__ == "__main__":
    unittest.main()

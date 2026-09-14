"""Admin-managed single-active-provider tests.

sqlite + in-process fake provider HTTP servers (no billable live
calls). Transport-call counting proves single-shot behaviour: the
selected provider+model is hit exactly once per inference, and no
other provider is ever dialled (no race, no fallback).
"""

import json
import logging
import os
import sqlite3
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import token_crypto  # noqa: E402
from conftest import make_client, mint_admin  # noqa: E402
from creative_intel import (  # noqa: E402
    dispatcher as dispatcher_mod,
)
from creative_intel import (
    ingest as ingest_mod,
)
from creative_intel import (
    provider_inventory as inv_mod,
)
from creative_intel import (
    providers as providers_mod,
)
from creative_intel import (
    schema as schema_mod,
)
from creative_intel.creative import blank_annotation, validate  # noqa: E402

ASK_GOOD = json.dumps({"answer": "Total spend is $400 across uploads.",
                       "used": ["totals", "campaigns"]})

CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
       "Link Clicks,Conversions,Platform\n"
       "A,a1,k1,100,10000,200,10,meta\n"
       "B,b1,k2,300,30000,300,15,tiktok\n")


def _structure_content():
    ann = blank_annotation()
    ann["hook_type"] = "question"
    ann["hook_modality"] = "spoken"
    ann["hook_confidence"] = 0.8
    ann["creator_vs_branded"] = "branded"
    ann["creator_confidence"] = 0.5
    ann["duration_s"] = 30.0
    ann["pace_cuts_per_min"] = 1.0
    assert validate(ann) == [], validate(ann)
    return json.dumps({k: ann[k] for k in
                       ("hook_type", "hook_modality", "hook_confidence",
                        "brand_seconds", "product_seconds", "logo_seconds",
                        "structure", "creator_vs_branded",
                        "creator_confidence", "duration_s",
                        "pace_cuts_per_min")})


class ChatStub(BaseHTTPRequestHandler):
    """OpenAI-compatible chat stub: records every call, never bills."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        self.server.calls.append(
            {"path": self.path,
             "authorization": self.headers.get("Authorization"),
             "x_api_key": self.headers.get("x-api-key"),
             "model": body.get("model"),
             "raw": raw.decode("utf-8", "replace")[:2000]})
        if self.server.fail:
            self._send(500, {"error": "vendor exploded"})
            return
        self._send(200, {"choices": [{"message": {
            "content": self.server.content}}]})

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class AnthropicStub(ChatStub):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        self.server.calls.append(
            {"path": self.path,
             "authorization": self.headers.get("Authorization"),
             "x_api_key": self.headers.get("x-api-key"),
             "model": body.get("model")})
        self._send(200, {"content": [{"type": "text",
                                      "text": self.server.content}]})


class ModelsStub(BaseHTTPRequestHandler):
    """Discovery stub: openai/gemini/ollama-tag shapes on one server."""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.calls.append(
            {"path": self.path,
             "authorization": self.headers.get("Authorization"),
             "x_goog": self.headers.get("x-goog-api-key"),
             "x_api_key": self.headers.get("x-api-key")})
        if self.server.fail:
            self._send(500, {"error": "down"})
            return
        shape = self.server.shape
        if shape == "gemini":
            payload = {"models": [{"name": "models/%s" % i}
                                  for i in self.server.ids]}
        elif shape == "ollama":
            payload = {"models": [{"name": i} for i in self.server.ids]}
        else:
            payload = {"data": [{"id": i} for i in self.server.ids]}
        self._send(200, payload)

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class _ComboStub(BaseHTTPRequestHandler):
    """One-port fake vendor: chat POST + /models|/v1/models GET."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            body = {}
        self.server.calls.append(
            {"method": "POST", "path": self.path,
             "authorization": self.headers.get("Authorization"),
             "model": body.get("model")})
        if self.server.fail:
            self._send(500, {"error": "vendor exploded"})
            return
        self._send(200, {"choices": [{"message": {
            "content": self.server.chat_content}}]})

    def do_GET(self):
        self.server.calls.append(
            {"method": "GET", "path": self.path,
             "authorization": self.headers.get("Authorization")})
        if self.server.fail:
            self._send(500, {"error": "down"})
            return
        self._send(200, {"data": [{"id": i}
                                  for i in self.server.models_ids]})

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_server(handler, **attrs):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    for key, value in attrs.items():
        setattr(srv, key, value)
    srv.calls = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv, thread, "http://127.0.0.1:%d" % srv.server_address[1]


def _posts(srv):
    """Chat (POST) calls only — discovery GETs are excluded."""
    return [c for c in srv.calls if c.get('method', 'POST') == 'POST']


def stop_server(srv, thread):
    srv.shutdown()
    thread.join(timeout=10)
    srv.server_close()


class LiveEnv:
    """live provider mode + throwaway master key for one test class."""

    @classmethod
    def push(cls):
        cls._saved = dict(os.environ)
        os.environ["CREATIVE_INTEL_PROVIDER_MODE"] = "live"
        os.environ["CREATIVE_INTEL_MASTER_KEY"] = (
            token_crypto.generate_master_key())

    @classmethod
    def pop(cls):
        os.environ.clear()
        os.environ.update(cls._saved)


class ApiBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        LiveEnv.push()

    @classmethod
    def tearDownClass(cls):
        LiveEnv.pop()

    def setUp(self):
        import tempfile
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self._tmp.name
        self._tmp.close()
        self.client = make_client(self.db_path)
        self.client.headers.update(mint_admin(self.db_path))
        self.admin_prefix = "/api/admin/providers"

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    # -- helpers ------------------------------------------------------
    def put(self, pid, payload):
        return self.client.put("%s/%s" % (self.admin_prefix, pid),
                               json=payload)

    def seed_csv(self):
        conn = sqlite3.connect(self.db_path)
        try:
            schema_mod.init_db(conn)
            ingest_mod.insert_rows(
                conn, ingest_mod.parse_csv(CSV, "meta"))
            conn.commit()
        finally:
            conn.close()

    def sql(self, stmt, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(stmt, args).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def stored_secret(self, pid):
        rows = self.sql("SELECT secret_enc FROM provider_configs"
                        " WHERE provider_id = ?", (pid,))
        return rows[0][0] if rows else None


class SecretsMaskedTest(ApiBase):
    def test_get_masks_and_put_encrypts(self):
        chat, chat_thread, chat_base = start_server(
            ChatStub, fail=False, content=ASK_GOOD)
        try:
            got = self.put("deepseek", {"secret": "sk-live-123",
                                        "base_url": chat_base})
            self.assertEqual(got.status_code, 200, got.text)
            # Ciphertext at rest, never the plaintext…
            enc = self.stored_secret("deepseek")
            self.assertIsNotNone(enc)
            self.assertNotIn("sk-live-123", enc)
            self.assertEqual(token_crypto.decrypt_secret(enc),
                             "sk-live-123")
            # …and zero secret material over the wire.
            got = self.client.get(self.admin_prefix + "/")
            self.assertEqual(got.status_code, 200, got.text)
            self.assertNotIn("sk-live-123", got.text)
            self.assertNotIn(enc, got.text)
            row = next(p for p in got.json()["providers"]
                       if p["provider_id"] == "deepseek")
            self.assertTrue(row["has_secret"])
            self.assertTrue(row["configured"])
            self.assertIsNone(got.json()["active"])
            # Unsupported entries expose no secret field at all.
            chatgpt = next(p for p in got.json()["providers"]
                           if p["provider_id"] == "chatgpt")
            self.assertFalse(chatgpt["supported"])
            self.assertNotIn("secret_enc", chatgpt)
            self.assertIn("unsupported_reason", chatgpt)
        finally:
            stop_server(chat, chat_thread)

    def test_auth_gates(self):
        from ci_backend.app import create_app
        from ci_backend.config import Settings
        from fastapi.testclient import TestClient

        anon = TestClient(create_app(self.db_path, Settings(
            workos_client_id="c", key_workos="[REDACTED]")),
            raise_server_exceptions=False)
        self.assertEqual(anon.get(self.admin_prefix + "/").status_code,
                         401)
        emp_cookie = mint_admin(self.db_path, email="emp@example.com",
                                role="employee")
        emp_client = make_client(self.db_path)
        emp_client.headers.update(emp_cookie)
        self.assertEqual(
            emp_client.get(self.admin_prefix + "/").status_code, 403)

    def test_no_secret_in_audit_log(self):
        logger = logging.getLogger("creative_intel.security")
        with self.assertLogs(logger, level="INFO") as captured:
            self.put("deepseek", {"secret": "sk-log-probe-1"})
        blob = "\n".join(captured.output)
        self.assertNotIn("sk-log-probe-1", blob)


class TestRefreshTest(ApiBase):
    def test_test_and_refresh_merge_prune(self):
        models, models_thread, models_base = start_server(
            ModelsStub, fail=False, shape="openai",
            ids=["deepseek-v4-flash", "deepseek-v4-pro",
                 "whisper-large-v3"])
        try:
            self.assertEqual(self.put(
                "deepseek", {"secret": "sk-t1",
                             "base_url": models_base}).status_code, 200)
            # /test: bounded probe returning latency + offered count,
            # Bearer auth asserted server-side below.
            got = self.client.post(self.admin_prefix + "/deepseek/test")
            self.assertEqual(got.status_code, 200, got.text)
            body = got.json()
            # whisper-* is filtered by the offered predicate.
            self.assertEqual(body["offered_count"], 2)
            self.assertIn("latency_ms", body)
            self.assertNotIn("sk-t1", got.text)
            self.assertEqual(models.calls[-1]["authorization"],
                             "Bearer sk-t1")
            # Seed a retired model, then refresh: merge keeps live∩
            # static, prunes the vanished id.
            self.sql("INSERT OR IGNORE INTO provider_model_cache"
                     " (provider_id, model_id, display, offered, fetched_at)"
                     " VALUES ('deepseek', 'retired-model', 'Retired', 1,"
                     " '2026-01-01T00:00:00+00:00')")
            got = self.client.post(
                self.admin_prefix + "/deepseek/refresh")
            self.assertEqual(got.status_code, 200, got.text)
            self.assertEqual(got.json()["offered_count"], 2)
            self.assertFalse(got.json()["stale"])
            ids = {r[0] for r in self.sql(
                "SELECT model_id FROM provider_model_cache"
                " WHERE provider_id = 'deepseek'")}
            self.assertEqual(ids, {"deepseek-v4-flash", "deepseek-v4-pro"})
            # Failed refresh preserves the last catalog verbatim
            # (rows + fetched_at kept) and marks stale + retry.
            before = self.sql("SELECT model_id, fetched_at FROM"
                              " provider_model_cache"
                              " WHERE provider_id = 'deepseek'")
            models.fail = True
            got = self.client.post(
                self.admin_prefix + "/deepseek/refresh")
            self.assertEqual(got.status_code, 502, got.text)
            self.assertTrue(got.json()["stale"])
            self.assertIn("refresh", got.json()["retry"])
            after = self.sql("SELECT model_id, fetched_at FROM"
                             " provider_model_cache"
                             " WHERE provider_id = 'deepseek'")
            self.assertEqual(sorted(before), sorted(after))
            self.assertNotIn("sk-t1", got.text)
        finally:
            stop_server(models, models_thread)

    def test_list_returns_cached_models_for_selector(self):
        # The model selector is fed by Refresh Models: GET must carry
        # the cached offered id/label pairs (stale ones included, so
        # the UI can badge them), never secret material.
        models, models_thread, models_base = start_server(
            ModelsStub, fail=False, shape="openai",
            ids=["deepseek-v4-flash", "deepseek-v4-pro"])
        try:
            self.assertEqual(self.put(
                "deepseek", {"secret": "sk-t1",
                             "base_url": models_base}).status_code, 200)
            got = self.client.post(
                self.admin_prefix + "/deepseek/refresh")
            self.assertEqual(got.status_code, 200, got.text)
            got = self.client.get(self.admin_prefix)
            self.assertEqual(got.status_code, 200, got.text)
            entry = [c for c in got.json()["providers"]
                     if c["provider_id"] == "deepseek"][0]
            cached = {m["id"]: m["label"] for m in entry["cached_models"]}
            self.assertEqual(set(cached), {"deepseek-v4-flash",
                                           "deepseek-v4-pro"})
            self.assertFalse(entry["stale"])
            self.assertNotIn("sk-t1", got.text)
        finally:
            stop_server(models, models_thread)

    def test_key_replace_fail_keeps_old_secret(self):
        models, models_thread, models_base = start_server(
            ModelsStub, fail=False, shape="openai",
            ids=["deepseek-v4-flash"])
        try:
            self.put("deepseek", {"secret": "sk-good",
                                  "base_url": models_base})
            self.client.post(self.admin_prefix + "/deepseek/refresh")
            self.client.post(self.admin_prefix + "/activate",
                             json={"provider_id": "deepseek",
                                   "model_id": "deepseek-v4-flash",
                                   "revision": 0})
            # New secret against a dead port: validation fails, the
            # ACTIVE config keeps serving the old secret.
            got = self.put("deepseek", {"secret": "sk-bad",
                                        "base_url": "http://127.0.0.1:9"})
            self.assertEqual(got.status_code, 502, got.text)
            self.assertEqual(token_crypto.decrypt_secret(
                self.stored_secret("deepseek")), "sk-good")
            got = self.client.post(self.admin_prefix + "/deepseek/test")
            self.assertEqual(got.status_code, 200, got.text)
            self.assertEqual(models.calls[-1]["authorization"],
                             "Bearer sk-good")
        finally:
            stop_server(models, models_thread)


class ActivateDeactivateTest(ApiBase):
    def _ready(self):
        models, models_thread, models_base = start_server(
            ModelsStub, fail=False, shape="openai",
            ids=["deepseek-v4-flash"])
        self.put("deepseek", {"secret": "sk-a",
                              "base_url": models_base})
        self.client.post(self.admin_prefix + "/deepseek/refresh")
        return models, models_thread

    def test_activate_conflict_and_deactivate(self):
        models, models_thread = self._ready()
        try:
            got = self.client.post(
                self.admin_prefix + "/activate",
                json={"provider_id": "deepseek",
                      "model_id": "deepseek-v4-flash", "revision": 0})
            self.assertEqual(got.status_code, 200, got.text)
            self.assertEqual(got.json()["current_revision"], 1)
            # Stale revision collides; the current revision is
            # returned for retry.
            got = self.client.post(
                self.admin_prefix + "/activate",
                json={"provider_id": "deepseek",
                      "model_id": "deepseek-v4-flash", "revision": 0})
            self.assertEqual(got.status_code, 409, got.text)
            self.assertEqual(got.json()["current_revision"], 1)
            # Unknown models and unsupported entries never activate.
            got = self.client.post(
                self.admin_prefix + "/activate",
                json={"provider_id": "deepseek",
                      "model_id": "nope-not-offered", "revision": 1})
            self.assertEqual(got.status_code, 409, got.text)
            got = self.client.post(
                self.admin_prefix + "/activate",
                json={"provider_id": "chatgpt",
                      "model_id": "gpt-5.6-sol", "revision": 1})
            self.assertEqual(got.status_code, 409, got.text)
            # Deactivate with a stale revision also collides…
            got = self.client.post(
                self.admin_prefix + "/deactivate",
                json={"revision": 0})
            self.assertEqual(got.status_code, 409, got.text)
            # …then pauses inference atomically.
            got = self.client.post(
                self.admin_prefix + "/deactivate",
                json={"revision": 1})
            self.assertEqual(got.status_code, 200, got.text)
            self.assertIsNone(got.json()["active"])
            self.assertEqual(got.json()["current_revision"], 2)
        finally:
            stop_server(models, models_thread)

    def test_remove_active_requires_confirm(self):
        models, models_thread = self._ready()
        try:
            self.client.post(self.admin_prefix + "/activate",
                             json={"provider_id": "deepseek",
                                   "model_id": "deepseek-v4-flash",
                                   "revision": 0})
            got = self.put("deepseek", {"secret": None})
            self.assertEqual(got.status_code, 409, got.text)
            self.assertTrue(got.json().get("confirm_required"))
            self.assertIsNotNone(self.stored_secret("deepseek"))
            got = self.put("deepseek", {"secret": None, "confirm": True})
            self.assertEqual(got.status_code, 200, got.text)
            self.assertIsNone(got.json()["active"])
            self.assertIsNone(self.stored_secret("deepseek"))
            self.assertEqual(
                self.sql("SELECT COUNT(*) FROM provider_model_cache"
                         " WHERE provider_id = 'deepseek'")[0][0], 0)
        finally:
            stop_server(models, models_thread)


class AdoptUnsupportedSsrfTest(ApiBase):
    def test_adopt_then_readopt_conflicts(self):
        os.environ["CREATIVE_INTEL_KEY_MOONSHOT"] = "legacy-kimi-1"
        try:
            got = self.client.post(self.admin_prefix + "/kimi/adopt")
            self.assertEqual(got.status_code, 200, got.text)
            self.assertTrue(got.json()["has_secret"])
            self.assertFalse(got.json()["activated"])
            self.assertNotIn("legacy-kimi-1", got.text)
            self.assertEqual(token_crypto.decrypt_secret(
                self.stored_secret("kimi")), "legacy-kimi-1")
            # One-time: a stored secret blocks re-adoption.
            got = self.client.post(self.admin_prefix + "/kimi/adopt")
            self.assertEqual(got.status_code, 409, got.text)
            # Nothing is activated by adoption.
            self.assertIsNone(
                self.client.get(self.admin_prefix + "/").json()["active"])
        finally:
            del os.environ["CREATIVE_INTEL_KEY_MOONSHOT"]

    def test_adopt_missing_source_and_blocked(self):
        got = self.client.post(self.admin_prefix + "/qwen/adopt")
        self.assertEqual(got.status_code, 409, got.text)
        self.assertIn("tried_env", got.json())
        for pid in ("chatgpt", "opencode", "ollama"):
            got = self.client.post("%s/%s/adopt" % (self.admin_prefix,
                                                    pid))
            self.assertEqual(got.status_code, 409, got.text)
        for pid in ("chatgpt", "opencode"):
            got = self.client.post(
                "%s/%s/test" % (self.admin_prefix, pid))
            self.assertEqual(got.status_code, 409, got.text)
            got = self.client.post(
                "%s/%s/refresh" % (self.admin_prefix, pid))
            self.assertEqual(got.status_code, 409, got.text)
            got = self.put(pid, {"secret": "x"})
            self.assertEqual(got.status_code, 409, got.text)
        got = self.client.post("%s/nope/test" % self.admin_prefix)
        self.assertEqual(got.status_code, 404, got.text)

    def test_ssrf_guard(self):
        for bad in ("http://169.254.169.254/x", "http://example.com/",
                    "ftp://127.0.0.1:11434/", "http://metadata.google.internal/"):
            got = self.put("ollama", {"base_url": bad})
            self.assertEqual(got.status_code, 409, got.text)
        # Loopback stays usable for local gateways.
        got = self.put("ollama", {"base_url": "http://127.0.0.1:11434"})
        self.assertEqual(got.status_code, 200, got.text)
        with self.assertRaises(ValueError):
            inv_mod.assert_safe_base_url("http://10.0.0.9:4000/v1")
        self.assertEqual(
            inv_mod.assert_safe_base_url(
                "http://10.0.0.9:4000/v1",
                allowlist="10.0.0.9"), "http://10.0.0.9:4000/v1")


class ManagedInferenceTest(ApiBase):
    """Employee inference hits ONLY the selected provider+model."""

    def _two_provider_world(self):
        # One port per fake vendor serves BOTH the chat shape and the
        # discovery shape (the stored base_url drives both paths).
        deep, deep_thread, deep_base = start_server(
            _ComboStub, fail=False, chat_content=ASK_GOOD,
            models_shape="openai", models_ids=["deepseek-v4-flash"])
        qwen, qwen_thread, qwen_base = start_server(
            _ComboStub, fail=False, chat_content=ASK_GOOD,
            models_shape="openai", models_ids=["qwen-turbo"])
        self.put("deepseek", {"secret": "sk-deep",
                              "base_url": deep_base})
        self.put("qwen", {"secret": "sk-qwen", "base_url": qwen_base})
        self.client.post(self.admin_prefix + "/deepseek/refresh")
        self.client.post(self.admin_prefix + "/qwen/refresh")
        self.client.post(self.admin_prefix + "/activate",
                         json={"provider_id": "deepseek",
                               "model_id": "deepseek-v4-flash",
                               "revision": 0})
        self.seed_csv()
        return (deep, deep_thread, qwen, qwen_thread)

    def test_ask_hits_only_selected_forged_params_ignored(self):
        deep, deep_thread, qwen, qwen_thread = self._two_provider_world()
        try:
            got = self.client.post(
                "/api/ask",
                json={"question": "what is spend?",
                      "provider_id": "qwen", "model_id": "qwen-turbo",
                      "endpoint": "http://evil.invalid/"})
            self.assertEqual(got.status_code, 200, got.text)
            self.assertIn("[LLM]", got.json()["answer"])
            # Exactly one selected call; the forged provider, model
            # and endpoint never fire.
            self.assertEqual(len(_posts(deep)), 1)
            self.assertEqual(len(_posts(qwen)), 0)
            call = _posts(deep)[0]
            self.assertEqual(call["model"], "deepseek-v4-flash")
            self.assertEqual(call["authorization"], "Bearer sk-deep")
            self.assertTrue(call["path"].endswith("/v1/chat/completions"))
            self.assertNotIn("sk-deep", got.text)
        finally:
            stop_server(deep, deep_thread)
            stop_server(qwen, qwen_thread)

    def test_chosen_model_failure_is_502_zero_calls_elsewhere(self):
        deep, deep_thread, qwen, qwen_thread = self._two_provider_world()
        try:
            deep.fail = True
            got = self.client.post("/api/ask",
                                   json={"question": "what is spend?"})
            self.assertEqual(got.status_code, 502, got.text)
            self.assertIn("[provider=deepseek]", got.json()["error"])
            self.assertNotIn("sk-deep", got.text)
            # The job system retries the SAME selection once; no
            # request ever reaches the other provider.
            self.assertEqual(len(_posts(deep)), 2)
            self.assertEqual(len(_posts(qwen)), 0)
        finally:
            stop_server(deep, deep_thread)
            stop_server(qwen, qwen_thread)

    def test_structure_hits_only_selected_single_shot(self):
        deep, deep_thread, qwen, qwen_thread = self._two_provider_world()
        try:
            deep.chat_content = _structure_content()
            llm = dispatcher_mod.ManagedLlm(db_path=self.db_path)
            ann = llm.structure("watch this demo deal",
                                [{"t_sec": 0.0, "brand_visible": True,
                                  "product_visible": False,
                                  "logo_visible": False,
                                  "text_overlay": "", "cta_visible": False,
                                  "end_frame": False, "cut": False}])
            self.assertEqual(ann["hook_type"], "question")
            self.assertEqual(len(_posts(deep)), 1)
            self.assertEqual(len(_posts(qwen)), 0)
            self.assertEqual(_posts(deep)[0]["model"],
                             "deepseek-v4-flash")
            # A failing chosen model raises with its provider id and
            # makes exactly one transport call (HTTP errors are never
            # retried — the vendor already did the work).
            deep.fail = True
            llm2 = dispatcher_mod.ManagedLlm(db_path=self.db_path)
            with self.assertRaises(providers_mod.ProviderUnavailable) as ctx:
                llm2.structure("x", [])
            self.assertIn("[provider=deepseek]", str(ctx.exception))
            self.assertEqual(len(_posts(deep)), 2)
            self.assertEqual(len(_posts(qwen)), 0)
        finally:
            stop_server(deep, deep_thread)
            stop_server(qwen, qwen_thread)

    def test_deactivate_pauses_ask_with_409(self):
        deep, deep_thread, qwen, qwen_thread = self._two_provider_world()
        try:
            self.client.post(self.admin_prefix + "/deactivate",
                             json={"revision": 1})
            got = self.client.post("/api/ask",
                                   json={"question": "what is spend?"})
            self.assertEqual(got.status_code, 409, got.text)
            self.assertIn("AI is not configured", got.json()["error"])
            self.assertEqual(len(_posts(deep)), 0)
            self.assertEqual(len(_posts(qwen)), 0)
        finally:
            stop_server(deep, deep_thread)
            stop_server(qwen, qwen_thread)

    def test_providers_bundle_prefers_managed_in_live(self):
        deep, deep_thread, qwen, qwen_thread = self._two_provider_world()
        try:
            prov = providers_mod.Providers(db_path=self.db_path)
            self.assertEqual(prov.mode, "live")
            self.assertIsInstance(prov.llm, dispatcher_mod.ManagedLlm)
            # STT/vision slots are untouched by the managed swap: the
            # legacy bundle (or its honest live-error placeholder)
            # still owns them — never mocks in live mode.
            self.assertNotIsInstance(prov.stt, providers_mod.MockStt)
            self.assertNotIsInstance(prov.vision,
                                     providers_mod.MockVision)
        finally:
            stop_server(deep, deep_thread)
            stop_server(qwen, qwen_thread)

    def test_live_bundle_without_selection_is_honest(self):
        prov = providers_mod.Providers(db_path=self.db_path)
        self.assertEqual(prov.mode, "live")
        with self.assertRaises(providers_mod.ProviderUnavailable) as ctx:
            prov.llm.ask_facts("q?", {"totals": {}})
        self.assertIn("AI is not configured", str(ctx.exception))


class DiscoverySchemeTest(ApiBase):
    def test_gemini_header_vs_bearer_schemes(self):
        gem, gem_thread, gem_base = start_server(
            ModelsStub, fail=False, shape="gemini",
            ids=["gemini-3.5-flash-lite", "gemini-2.5-flash"])
        bea, bea_thread, bea_base = start_server(
            ModelsStub, fail=False, shape="openai",
            ids=["deepseek-v4-flash"])
        try:
            offered, _lat = dispatcher_mod.probe_provider(
                "gemini", "g-secret", gem_base)
            # Gemini discovery uses x-goog-api-key (model_sync
            # scheme), never a Bearer Authorization header…
            self.assertEqual(gem.calls[-1]["x_goog"], "g-secret")
            self.assertIsNone(gem.calls[-1]["authorization"])
            self.assertTrue(gem.calls[-1]["path"].endswith(
                "/v1beta/models"))
            self.assertEqual(offered[0]["id"],
                             "gemini-3.5-flash-lite")
            self.assertEqual(offered[0]["label"],
                             "Gemini 3.5 Flash-Lite")
            # …while OpenAI-shaped vendors use Bearer.
            dispatcher_mod.probe_provider("deepseek", "sk-x", bea_base)
            self.assertEqual(bea.calls[-1]["authorization"],
                             "Bearer sk-x")
        finally:
            stop_server(gem, gem_thread)
            stop_server(bea, bea_thread)

    def test_ollama_tags_shape_keyless(self):
        tags, tags_thread, tags_base = start_server(
            ModelsStub, fail=False, shape="ollama",
            ids=["llama3.1:8b", "qwen3:8b"])
        try:
            offered, _lat = dispatcher_mod.probe_provider(
                "ollama", None, tags_base)
            self.assertEqual(
                {m["id"] for m in offered}, {"llama3.1:8b", "qwen3:8b"})
            self.assertIsNone(tags.calls[-1]["authorization"])
            self.assertTrue(tags.calls[-1]["path"].endswith("/api/tags"))
        finally:
            stop_server(tags, tags_thread)

    def test_anthropic_chat_uses_x_api_key(self):
        chat, chat_thread, chat_base = start_server(
            AnthropicStub, fail=False, content=ASK_GOOD)
        try:
            client = providers_mod.make_chat(
                "anthropic", "claude-haiku-4-5", secret="a-secret",
                base_url=chat_base)
            text = client.chat([{"role": "user", "content": "hi"}])
            self.assertIn("Total spend", text)
            self.assertEqual(chat.calls[-1]["x_api_key"], "a-secret")
            self.assertIsNone(chat.calls[-1]["authorization"])
            self.assertEqual(chat.calls[-1]["model"],
                             "claude-haiku-4-5")
        finally:
            stop_server(chat, chat_thread)

    def test_gemini_chat_uses_key_param(self):
        client = providers_mod.make_chat("gemini", "gemini-3.5-flash-lite",
                                         secret="g-secret",
                                         base_url="http://127.0.0.1:9")
        self.assertIn("?key=", client.url)
        self.assertIn("gemini-3.5-flash-lite", client.url)


class DispatcherUnitTest(ApiBase):
    def _seed(self, provider_id, model_id, secret=None, fetched_at=None,
              offered_models=()):
        import datetime

        now = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        if secret is not None:
            self.sql("UPDATE provider_configs SET secret_enc = ?,"
                     " secret_updated_at = ? WHERE provider_id = ?",
                     (token_crypto.encrypt_secret(secret), now,
                      provider_id))
        self.sql("INSERT OR REPLACE INTO active_provider_selection"
                 " (id, provider_id, model_id, revision, updated_by,"
                 " updated_at) VALUES (1, ?, ?, 1, 'test', ?)",
                 (provider_id, model_id, now))
        for mid in offered_models:
            self.sql("INSERT OR REPLACE INTO provider_model_cache"
                     " (provider_id, model_id, display, offered, fetched_at)"
                     " VALUES (?, ?, ?, 1, ?)",
                     (provider_id, mid, mid,
                      fetched_at or now))

    def test_stale_cache_and_mismatch_fail_closed(self):
        self._seed("deepseek", "deepseek-v4-flash", secret="sk-s",
                   fetched_at="2020-01-01T00:00:00+00:00",
                   offered_models=["deepseek-v4-flash"])
        with self.assertRaises(providers_mod.ProviderUnavailable) as ctx:
            dispatcher_mod.ManagedLlm(
                db_path=self.db_path).ask_facts("q?", {})
        self.assertIn("stale", str(ctx.exception))
        # Exact-model-only: a near-miss id is not a match.
        self._seed("deepseek", "deepseek-v4-flas", secret="sk-s",
                   offered_models=["deepseek-v4-flash"])
        with self.assertRaises(providers_mod.ProviderUnavailable) as ctx:
            dispatcher_mod.ManagedLlm(
                db_path=self.db_path).ask_facts("q?", {})
        self.assertIn("not in the offered catalog", str(ctx.exception))

    def test_no_selection_fails_honest(self):
        with self.assertRaises(providers_mod.ProviderUnavailable) as ctx:
            dispatcher_mod.ManagedLlm(
                db_path=self.db_path).ask_facts("q?", {})
        self.assertEqual(str(ctx.exception),
                         inv_mod.NOT_CONFIGURED_MESSAGE)

    def test_network_error_retries_once_same_selection(self):
        self._seed("deepseek", "deepseek-v4-flash", secret="sk-s",
                   offered_models=["deepseek-v4-flash"])
        llm = dispatcher_mod.ManagedLlm(db_path=self.db_path)
        # Patch make_chat to a client that always fails at the
        # network level: exactly 2 transport calls (1 + 1 retry).
        calls = []

        class Dead:
            def chat(self, messages, max_tokens=0):
                calls.append(1)
                raise providers_mod.ProviderUnavailable(
                    "unreachable 127.0.0.1: [Errno 61] refused")

        real = providers_mod.make_chat
        providers_mod.make_chat = lambda *a, **k: Dead()
        try:
            with self.assertRaises(providers_mod.ProviderUnavailable) \
                    as ctx:
                llm.ask_facts("q?", {})
        finally:
            providers_mod.make_chat = real
        self.assertEqual(len(calls), 2)
        self.assertIn("[provider=deepseek]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

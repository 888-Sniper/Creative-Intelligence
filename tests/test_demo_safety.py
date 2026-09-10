"""Demo/production fail-closed config + provider readiness endpoint."""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend.app import create_app
from ci_backend.config import ConfigError, Settings
from ci_backend.main import resolve_sync_every


def demo_settings(**over):
    base = dict(environment="demo", provider_mode="live",
                cookie_secure=True, admin_email="boss@foap.test",
                workos_client_id="client_x", key_workos="sk_test_x",
                workos_redirect_uri="https://x.example/api/auth/callback")
    base.update(over)
    return Settings(**base)


class DemoSafetyTest(unittest.TestCase):
    def test_local_is_unaffected(self):
        Settings().require_public_safety()

    def test_demo_mock_fails_closed(self):
        with self.assertRaises(ConfigError) as ctx:
            demo_settings(provider_mode="mock").require_public_safety()
        self.assertIn("CREATIVE_INTEL_PROVIDER_MODE", str(ctx.exception))

    def test_demo_requires_secure_cookie_and_identity(self):
        with self.assertRaises(ConfigError) as ctx:
            demo_settings(cookie_secure=False,
                          admin_email="").require_public_safety()
        msg = str(ctx.exception)
        self.assertIn("CREATIVE_INTEL_COOKIE_SECURE", msg)
        self.assertIn("CREATIVE_INTEL_ADMIN_EMAIL", msg)

    def test_secret_values_never_appear_in_messages(self):
        with self.assertRaises(ConfigError) as ctx:
            demo_settings(provider_mode="mock").require_public_safety()
        self.assertNotIn("sk_test_x", str(ctx.exception))

    def test_valid_demo_passes(self):
        demo_settings().require_public_safety()

    def test_create_app_refuses_unsafe_demo(self):
        with self.assertRaises(ConfigError):
            create_app("/tmp/ci-demo-refused.db",
                       demo_settings(provider_mode="mock"))


class ResolveSyncEveryTest(unittest.TestCase):
    def test_explicit_flag_wins_over_env(self):
        args = types.SimpleNamespace(sync_every=60)
        self.assertEqual(resolve_sync_every(args, Settings(sync_every=3600)),
                         60)

    def test_env_setting_applies_without_flag(self):
        args = types.SimpleNamespace(sync_every=0)
        self.assertEqual(resolve_sync_every(args, Settings(sync_every=3600)),
                         3600)

    def test_zero_disables(self):
        args = types.SimpleNamespace(sync_every=0)
        self.assertEqual(resolve_sync_every(args, Settings()), 0)

    def test_bad_env_value_disables(self):
        args = types.SimpleNamespace(sync_every=0)
        settings = Settings()
        settings.sync_every = "hourly"
        self.assertEqual(resolve_sync_every(args, settings), 0)


if __name__ == "__main__":
    unittest.main()

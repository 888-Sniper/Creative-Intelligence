"""Master-key envelope encryption unit tests (no keychain, no network)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import token_crypto  # noqa: E402
from ci_backend.config import Settings  # noqa: E402

TEST_MASTER_KEY = "r6I4teiO8U9i7HlJkR4tLghv5kqp69HfLWMcczM8UUs="
OTHER_MASTER_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _settings(key=TEST_MASTER_KEY):
    return Settings(master_key=key)


def test_roundtrip():
    enc = token_crypto.encrypt_secret("s3cr3t", _settings())
    assert enc and enc != "s3cr3t"
    assert token_crypto.decrypt_secret(enc, _settings()) == "s3cr3t"


def test_ciphertext_differs_per_encryption():
    assert token_crypto.encrypt_secret("x", _settings()) != \
        token_crypto.encrypt_secret("x", _settings())


def test_wrong_key_fails_closed():
    enc = token_crypto.encrypt_secret("s3cr3t", _settings())
    with pytest.raises(token_crypto.CryptoError):
        token_crypto.decrypt_secret(enc, _settings(OTHER_MASTER_KEY))


def test_empty_token_fails_closed():
    with pytest.raises(token_crypto.CryptoError):
        token_crypto.decrypt_secret("", _settings())


def test_invalid_master_key_fails_closed():
    with pytest.raises(token_crypto.CryptoError):
        token_crypto.encrypt_secret("s3cr3t", _settings("not-a-key"))


def test_missing_master_key_names_env(monkeypatch):
    monkeypatch.delenv("CREATIVE_INTEL_MASTER_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "keyring", None)
    with pytest.raises(token_crypto.CryptoError) as ctx:
        token_crypto.encrypt_secret("s3cr3t", Settings(master_key=""))
    assert "CREATIVE_INTEL_MASTER_KEY" in str(ctx.value)

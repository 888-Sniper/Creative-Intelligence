"""AI providers (Nextly parity, trimmed to this tool's needs).

- Mock mode is the daily default; live requires provider_mode=live.
- Secrets live in the OS keychain (env override for local dev only).
  Status reports configured/missing — key values never leave this module.
- Live with missing keys is unavailable; it never falls back to mocks.
- Active/Fallback race: first token from the Active set wins, stalled
  sets fall through to Fallback. Mock responder backs demos and replay.
"""

import os

PROVIDER_MODE = os.environ.get("CP_PROVIDER_MODE", "mock")

CATALOG = {
    "deepseek": {"active": "deepseek-v4-flash",
                 "fallback": "deepseek-v4-pro",
                 "base_url": "https://api.deepseek.com",
                 "secret": "DEEPSEEK_API_KEY"},
    "kimi": {"active": "kimi-k2.7-code-highspeed", "fallback": "kimi-k3",
             "base_url": "https://api.moonshot.ai/v1",
             "secret": "MOONSHOT_API_KEY"},
    "gemini": {"active": "gemini-3.5-flash-lite",
               "fallback": "gemini-3.7-flash",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/models",
               "secret": "GEMINI_API_KEY"},
    "openai": {"active": "gpt-5.6-luna", "fallback": "gpt-5.6-sol",
               "base_url": "https://api.openai.com/v1",
               "secret": "OPENAI_API_KEY"},
    "claude": {"active": "claude-haiku-4-5", "fallback": "claude-opus-5",
               "base_url": "https://api.anthropic.com",
               "secret": "ANTHROPIC_API_KEY"},
    "groq": {"active": "llama-3.3-70b-versatile",
             "fallback": "llama-3.1-8b-instant",
             "base_url": "https://api.groq.com/openai/v1",
             "secret": "GROQ_API_KEY"},
    "openrouter": {"active": "google/gemini-2.5-flash-lite",
                   "fallback": "anthropic/claude-sonnet-4.5",
                   "base_url": "https://openrouter.ai/api/v1",
                   "secret": "OPENROUTER_API_KEY"},
    "ollama": {"active": None, "fallback": None,
               "base_url": "http://127.0.0.1:11434",
               "secret": None},
}

# Ids that do not reason unless asked keep the smaller cue cap.
QUIET_IDS = {"gemini-2.5-flash-lite", "claude-3", "claude-haiku-4-5",
             "claude-sonnet-4-6", "claude-opus-4-6", "gpt-4o",
             "deepseek-chat", "llama-3.3-70b-versatile"}
CUE_CAP_DEFAULT = 2048
CUE_CAP_QUIET = 1024


def _read_secret(name):
    """Local-dev secret source. Production reads the OS keychain instead;
    either way only presence is ever reported, never the value."""
    if not name:
        return None
    return os.environ.get("CP_SECRET_" + name)


def status():
    """Configured/missing per provider. Values are never included."""
    return {name: ("configured" if _read_secret(spec["secret"]) else "missing")
            for name, spec in CATALOG.items()}


def cue_cap(model_id):
    return CUE_CAP_QUIET if model_id in QUIET_IDS else CUE_CAP_DEFAULT


def mock_respond(prompt, model="mock-catalog-speed-pick"):
    return {"model": model, "text": f"[mock] {prompt[:120]}",
            "live": False}


def race(prompt, enabled, mode=None):
    """Active/Fallback race. Returns a response dict or raises."""
    mode = mode or PROVIDER_MODE
    if mode == "mock":
        return mock_respond(prompt)
    live = [p for p in enabled
            if p in CATALOG and status().get(p) == "configured"]
    if not live:
        raise RuntimeError("unavailable: no enabled provider has a stored "
                           "key; live never falls back to mocks")
    provider = live[0]
    return {"model": CATALOG[provider]["active"], "text": f"[live-stub] "
            f"{prompt[:120]}", "live": True, "provider": provider,
            "cue_cap": cue_cap(CATALOG[provider]["active"])}

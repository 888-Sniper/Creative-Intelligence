"""Provider adapters mirroring Nextly AI docs/PROVIDERS.md.

Mock implementations are first-class in mock mode. Live adapters fail
closed when the Keychain key is missing or provider_mode != live: they
raise ProviderUnavailable instead of silently returning mocks.
"""

import concurrent.futures
import json
import os
import subprocess
import time

LIVE_MODEL_IDS = {
    # Active defaults per provider, copied from Nextly docs/PROVIDERS.md.
    "deepseek": "deepseek-v4-flash", "kimi": "kimi-k2.7-code-highspeed",
    "grok": "grok-4.6", "qwen": "qwen-turbo", "glm": "glm-4.7-flash",
    "openrouter": "google/gemini-2.5-flash-lite", "nvidia": "meta/muse-glimmer-30b",
    "gemini": "gemini-3.5-flash-lite", "openai": "gpt-5.6-luna",
    "claude": "claude-haiku-4-5",
}

# Per-provider Keychain services (see docs/PROVIDERS.md). Secrets never
# enter the repo; only presence is probed, values are never read.
KEYCHAIN_IDS = {
    "deepgram": "creative-intel-deepgram",
    "groq-whisper": "creative-intel-groq-stt",
    "gemini": "creative-intel-gemini",
    "nvidia": "creative-intel-nvidia",
    "openai": "creative-intel-openai",
    "anthropic": "creative-intel-anthropic",
    "zai": "creative-intel-zai",
    "deepseek": "creative-intel-deepseek",
    "moonshot": "creative-intel-moonshot",
    "xai": "creative-intel-xai",
    "teamorouter": "creative-intel-teamorouter",
    "openrouter": "creative-intel-openrouter",
    "litellm": "creative-intel-litellm",
}

# Capability groups used by key_status() / LiveBundle.
GROUPS = {
    "stt": ("deepgram", "groq-whisper"),
    "vision": ("gemini", "nvidia", "openai", "anthropic", "zai"),
    "llm": ("deepseek", "moonshot", "xai", "gemini", "openai",
            "anthropic", "teamorouter", "openrouter"),
}

# Full Active/Fallback registry: (kind, active_model, fallback_model).
# "local" kind needs no key; "gateway" covers TeamoRouter/OpenRouter/LiteLLM.
REGISTRY = {
    "deepgram": ("transcription", "flux-general-en", "nova-3"),
    "groq-whisper": ("transcription", "whisper-large-v3-turbo",
                     "whisper-large-v3"),
    "gemini": ("vision+generation", "gemini-3.5-flash-lite",
               "gemini-3.7-flash"),
    "muse-glimmer": ("vision", "meta/muse-glimmer-30b",
                     "meta/muse-glimmer-30b"),
    "gpt": ("vision+generation", "gpt-5.6-luna", "gpt-5.6-sol"),
    "claude": ("vision+generation", "claude-haiku-4-5", "claude-opus-5"),
    "glm-5v": ("vision", "glm-5v-turbo", "glm-5.2"),
    "deepseek": ("generation", "deepseek-v4-flash", "deepseek-v4-pro"),
    "kimi": ("generation", "kimi-k2.7-code-highspeed", "kimi-k3"),
    "grok": ("generation", "grok-4.6", "grok-4.6"),
    "teamorouter": ("gateway", "deepseek-v4-flash-free",
                    "deepseek-v4-pro-free"),
    "openrouter": ("gateway", "google/gemini-2.5-flash-lite",
                   "anthropic/claude-sonnet-4.5"),
    "ollama": ("local", "(host models)", "(host models)"),
    "litellm": ("gateway", "(proxy models)", "(proxy models)"),
}

REGISTRY_KEYCHAIN = {"muse-glimmer": "nvidia", "gpt": "openai",
                     "claude": "anthropic", "glm-5v": "zai",
                     "kimi": "moonshot", "grok": "xai"}

MODELS_SYNC_TTL_S = 24 * 3600
FALLBACK_TIMEOUT_S = 8.0
RACE_TIMEOUT_S = 20.0
SYNC_STATE_PATH = os.path.expanduser(
    "~/.cache/creative-intel/models_sync.json")


class ProviderUnavailable(Exception):
    pass


def mode():
    return "live" if os.environ.get("provider_mode") == "live" else "mock"


def keychain_has(service):
    """Presence probe only: never reads the secret value into memory."""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service],
            capture_output=True, timeout=10)
        return out.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def keychain_secret(service):
    """Legacy presence check kept for callers; returns True/None, never secrets."""
    key = KEYCHAIN_IDS.get(service, service)
    return True if keychain_has(key) else None


def key_status():
    status = {}
    for group, members in GROUPS.items():
        ok = any(keychain_has(KEYCHAIN_IDS[m]) for m in members)
        status[group] = "configured" if ok else "missing"
    return status


def provider_matrix():
    """One row per registry entry for the providers view / health checks."""
    rows = []
    for name, (kind, active, fallback) in REGISTRY.items():
        if name == "ollama":
            state = "configured"  # local, keyless
        elif mode() != "live":
            state = "mock"
        else:
            svc = KEYCHAIN_IDS.get(REGISTRY_KEYCHAIN.get(name, name), "")
            state = "configured" if keychain_has(svc) else "missing"
        rows.append({"provider": name, "kind": kind,
                     "active_model": active, "fallback_model": fallback,
                     "status": state, "sync_due": models_sync_due(name),
                     "cue_cap_tokens": cue_cap_tokens(active)})
    return rows


def cue_cap_tokens(model):
    """max_tokens 2048 default; 1024 for ids that never think unless asked."""
    low = (model or "").lower()
    if any(tag in low for tag in
           ("gpt-4o", "deepseek-chat", "llama-3", "gemini-2.5-flash-lite",
            "claude-3", "claude-haiku-4", "claude-sonnet-4",
            "claude-opus-4")):
        return 1024
    return 2048


def thinking_params(provider, model):
    """Reasoning controls per vendor. Traces never reach the cue."""
    if provider == "deepseek":
        if model == "deepseek-v4-flash":
            return {"extra_body": {"thinking": {"type": "disabled"}}}
        return {"reasoning_effort": "low"}
    if provider == "openrouter":
        return {"reasoning": {"effort": "low", "exclude": True}}
    if provider == "claude":
        return {} if model == "claude-haiku-4-5" else {
            "output_config": {"effort": "low"}}
    if provider == "gemini":
        return {"thinkingLevel": "LOW"}
    return {}


def _last_sync():
    try:
        with open(SYNC_STATE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def models_sync_due(provider):
    state = _last_sync()
    return (time.time() - state.get(provider, 0)) > MODELS_SYNC_TTL_S


def record_models_sync(provider, models=()):
    os.makedirs(os.path.dirname(SYNC_STATE_PATH), exist_ok=True)
    state = _last_sync()
    state[provider] = time.time()
    with open(SYNC_STATE_PATH, "w") as fh:
        json.dump(state, fh)


def race(active, fallback, call, timeout=FALLBACK_TIMEOUT_S):
    """Race Active roster for first truthy result; else race Fallback.

    Returns (winner, value) or (None, None) when all are unavailable.
    """
    def _race(roster, budget):
        if not roster:
            return None, None
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(roster)) as pool:
            future_of = {pool.submit(call, item): item for item in roster}
            try:
                for done in concurrent.futures.as_completed(
                        future_of, timeout=budget):
                    try:
                        value = done.result()
                    except Exception:
                        continue
                    if value:
                        pool.shutdown(wait=False, cancel_futures=True)
                        return future_of[done], value
            except TimeoutError:
                pass
        return None, None

    winner, value = _race(active, timeout)
    return (winner, value) if value else _race(fallback, RACE_TIMEOUT_S)


class MockStt:
    def transcribe(self, creative_key):
        return ("mock transcript for %s: hook in first three seconds, demo, offer cta"
                % creative_key, 0.5)


class MockVision:
    def sample_frames(self, creative_key, every_s=3.0, duration_s=30.0):
        n = max(1, int(duration_s / every_s))
        return [{"t_sec": round(i * every_s, 1)} for i in range(n)]

    def annotate(self, frames):
        return [{"t_sec": f["t_sec"], "label": "mock-frame",
                 "brand_visible": f["t_sec"] < 3.0, "confidence": 0.5}
                for f in frames]


class MockLlm:
    def structure(self, transcript, labels):
        from .creative import blank_annotation
        ann = blank_annotation()
        text = (transcript or "").lower()
        if "?" in text or text.startswith(("what", "why", "how", "ever")):
            ann["hook_type"] = "question"
        elif any(w in text for w in ("demo", "watch", "show")):
            ann["hook_type"] = "demo_open"
        elif any(w in text for w in ("offer", "off", "deal", "sale")):
            ann["hook_type"] = "offer"
        ann["hook_confidence"] = 0.55
        ann["creator_confidence"] = 0.5
        brand = [l["t_sec"] for l in labels if l.get("brand_visible")]
        if brand:
            ann["brand_seconds"] = [{"start_s": min(brand), "end_s": max(brand),
                                     "modality": "V"}]
        ann["structure"]["hook"] = {"start_s": 0.0, "end_s": 3.0, "confidence": 0.6}
        ann["structure"]["cta"] = {"start_s": 25.0, "end_s": 30.0, "confidence": 0.5}
        ann["duration_s"] = 30.0
        return ann


class LiveBundle:
    """Placeholder live bundle: raises until live clients are wired.

    Wiring notes live in Docs/Providers.md; model ids in LIVE_MODEL_IDS.
    """

    def __init__(self):
        missing = [k for k, v in key_status().items() if v != "configured"]
        if mode() != "live":
            raise ProviderUnavailable("provider_mode != live (mock is active)")
        if missing:
            raise ProviderUnavailable("missing Keychain keys: %s" % missing)
        raise ProviderUnavailable("live clients not wired yet; add per-provider"
                                  " HTTP clients per Docs/Providers.md")


class Providers:
    def __init__(self):
        self.mode = mode()
        self.stt = MockStt()
        self.vision = MockVision()
        self.llm = MockLlm()

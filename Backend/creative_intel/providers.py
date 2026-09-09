"""Provider adapters mirroring Nextly AI docs/PROVIDERS.md.

Mock implementations are first-class in mock mode. Live adapters fail
closed when the Keychain key is missing or provider_mode != live: they
raise ProviderUnavailable instead of silently returning mocks.
"""

import base64
import concurrent.futures
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

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
    def transcribe(self, creative_key, audio_bytes=None, mime=None,
                   timings_out=None):
        return ("mock transcript for %s: hook in first three seconds, demo, offer cta"
                % creative_key, 0.5)


class MockVision:
    def sample_frames(self, creative_key, every_s=3.0, duration_s=30.0):
        n = max(1, int(duration_s / every_s))
        return [{"t_sec": round(i * every_s, 1)} for i in range(n)]

    def annotate(self, frames, images=None):
        return [{"t_sec": f["t_sec"], "label": "mock-frame",
                 "brand_visible": f["t_sec"] < 3.0, "confidence": 0.5,
                 "product_visible": False, "logo_visible": False,
                 "text_overlay": "", "cta_visible": False,
                 "end_frame": False, "cut": False}
                for f in frames]


class MockLlm:
    def structure(self, transcript, labels):
        from .creative import blank_annotation
        ann = blank_annotation()
        ann["hook_modality"] = "unknown"
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
        product = [l["t_sec"] for l in labels if l.get("product_visible")]
        if product:
            ann["product_seconds"] = [{"start_s": min(product),
                                       "end_s": max(product),
                                       "modality": "V"}]
        logo = [l["t_sec"] for l in labels if l.get("logo_visible")]
        if logo:
            ann["logo_seconds"] = [{"start_s": min(logo),
                                    "end_s": max(logo), "modality": "V"}]
        cta = [l["t_sec"] for l in labels if l.get("cta_visible")]
        if cta:
            ann["structure"]["cta"] = {"start_s": min(cta),
                                       "end_s": max(cta), "confidence": 0.5}
        ends = [l["t_sec"] for l in labels if l.get("end_frame")]
        if ends:
            ann["structure"]["endframe"] = {"start_s": min(ends),
                                            "end_s": max(ends),
                                            "confidence": 0.5}
        ann["structure"]["hook"] = {"start_s": 0.0, "end_s": 3.0, "confidence": 0.6}
        if not cta:
            ann["structure"]["cta"] = {"start_s": 25.0, "end_s": 30.0,
                                       "confidence": 0.5}
        ann["duration_s"] = 30.0
        return ann


def _env_key_name(service):
    short = service
    if short.startswith("creative-intel-"):
        short = short[len("creative-intel-"):]
    return "CREATIVE_INTEL_KEY_" + short.upper().replace("-", "_")


def _env_base_name(provider):
    return "CREATIVE_INTEL_BASE_" + provider.upper().replace("-", "_")


def live_secret(service):
    """Secret value for a Keychain service (never logs it).

    Environment override first (CI / non-macOS), else macOS Keychain
    via `security -w`. Returns None when unavailable: callers fail
    closed. The value is never written to logs, errors, or the repo.
    """
    env = os.environ.get(_env_key_name(service))
    if env:
        return env
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True, timeout=10, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    val = (out.stdout or "").strip()
    return val if out.returncode == 0 and val else None


def live_base(provider, default):
    """Endpoint base: env override (tests/stubs/proxies) else default."""
    return os.environ.get(_env_base_name(provider)) or default


HTTP_TIMEOUT_S = 30.0


def _http_json(url, payload=None, headers=None, timeout=HTTP_TIMEOUT_S):
    """POST (dict payload) or GET (None); returns decoded JSON. No logging."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}),
                                 method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            detail = ""
        raise ProviderUnavailable("HTTP %s from %s: %s"
                                  % (e.code, _host_of(url), detail))
    except OSError as e:
        raise ProviderUnavailable("unreachable %s: %s" % (_host_of(url), e))


def _host_of(url):
    try:
        return urllib.request.urlparse(url).netloc
    except Exception:
        return "provider"


def _extract_json(text):
    """First {...} object in model output; raises ProviderUnavailable."""
    if not isinstance(text, str):
        raise ProviderUnavailable("non-text model output")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ProviderUnavailable("no JSON object in model output")
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        raise ProviderUnavailable("model output is not valid JSON")


# Provider -> wiring. default_base=None means env-only (private proxy);
# the provider stays unavailable until CREATIVE_INTEL_BASE_<NAME> is set.
ENDPOINTS = {
    "deepgram": {"kind": "stt", "base": "https://api.deepgram.com",
                 "key": "creative-intel-deepgram"},
    "groq-whisper": {"kind": "stt", "base": "https://api.groq.com",
                     "key": "creative-intel-groq-stt"},
    "gemini": {"kind": "chat", "base": "https://generativelanguage.googleapis.com",
               "key": "creative-intel-gemini", "native": "gemini"},
    "nvidia": {"kind": "chat", "base": "https://integrate.api.nvidia.com",
               "key": "creative-intel-nvidia", "path": "/v1/chat/completions"},
    "openai": {"kind": "chat", "base": "https://api.openai.com",
               "key": "creative-intel-openai", "path": "/v1/chat/completions"},
    "anthropic": {"kind": "chat", "base": "https://api.anthropic.com",
                  "key": "creative-intel-anthropic", "native": "anthropic"},
    "zai": {"kind": "chat", "base": "https://open.bigmodel.cn",
            "key": "creative-intel-zai", "path": "/api/paas/v4/chat/completions"},
    "deepseek": {"kind": "chat", "base": "https://api.deepseek.com",
                 "key": "creative-intel-deepseek", "path": "/v1/chat/completions"},
    "moonshot": {"kind": "chat", "base": "https://api.moonshot.ai",
                 "key": "creative-intel-moonshot", "path": "/v1/chat/completions"},
    "xai": {"kind": "chat", "base": "https://api.x.ai",
            "key": "creative-intel-xai", "path": "/v1/chat/completions"},
    "teamorouter": {"kind": "chat", "base": None,
                    "key": "creative-intel-teamorouter",
                    "path": "/v1/chat/completions"},
    "openrouter": {"kind": "chat", "base": "https://openrouter.ai",
                   "key": "creative-intel-openrouter",
                   "path": "/api/v1/chat/completions"},
    "litellm": {"kind": "chat", "base": None,
                "key": "creative-intel-litellm", "path": "/v1/chat/completions"},
    "ollama": {"kind": "chat", "base": "http://127.0.0.1:11434",
               "key": None, "path": "/v1/chat/completions"},
}

VISION_PROMPT = (
    "You analyse ad-creative frames. Reply with ONE JSON object only: "
    '{"frames": [{"t_sec": <number>, "label": "<short>", '
    '"brand_visible": <true|false>, '
    '"product_visible": <true|false>, '
    '"logo_visible": <true|false>, '
    '"text_overlay": "<on-screen copy, or empty>", '
    '"cta_visible": <true|false>, '
    '"end_frame": <true if this looks like the closing card/frame>, '
    '"cut": <true if the scene changed since the previous frame>, '
    '"confidence": <0..1>}]}. '
    "One entry per supplied image, in order; t_sec values are: %s. "
    "Flag product shots, logo appearances, overlaid text, calls to "
    "action and the end frame explicitly — do not leave that to "
    "guesswork downstream.")

STRUCTURE_PROMPT = (
    "You structure ad-creative analysis. Reply with ONE JSON object only "
    "using exactly these keys: hook_type (one of question, bold_claim, "
    "demo_open, social_proof, offer, story, pattern_interrupt, other), "
    "hook_modality (visual if the hook lands on-screen, spoken if it is "
    "said in the transcript, text if it is overlaid copy, unknown if "
    "unclear), "
    "hook_confidence (0..1), brand_seconds/product_seconds/logo_seconds "
    "(arrays of {start_s, end_s} — derive them from the per-frame "
    "brand_visible/product_visible/logo_visible flags at their t_sec "
    "values, never from the free-text labels alone), structure "
    "(object with hook, body, demo, supers, cta, endframe, voiceover "
    "each {start_s, end_s, confidence} — set cta/endframe from the "
    "cta_visible/end_frame flags and text_overlay copy), "
    "creator_vs_branded (creator|branded|hybrid), "
    "creator_confidence (0..1), duration_s, pace_cuts_per_min "
    "(count the frames with cut=true). "
    "Transcript: %s\nVision labels: %s")


class OpenAiChat:
    """OpenAI-compatible chat client (OpenAI, NVIDIA, DeepSeek, Kimi,
    Grok, Zhipu, OpenRouter, LiteLLM proxies, Ollama)."""

    def __init__(self, provider, model):
        cfg = ENDPOINTS[provider]
        base = live_base(provider, cfg["base"])
        if not base:
            raise ProviderUnavailable(
                "%s needs %s set (private proxy base)" % (
                    provider, _env_base_name(provider)))
        self.url = base.rstrip("/") + cfg["path"]
        self.key = live_secret(cfg["key"]) if cfg["key"] else None
        if cfg["key"] and not self.key:
            raise ProviderUnavailable("missing key for %s" % provider)
        self.model = model

    def chat(self, messages, max_tokens=2048):
        headers = {}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        body = {"model": self.model, "messages": messages,
                "max_tokens": max_tokens, "temperature": 0.2}
        got = _http_json(self.url, body, headers)
        try:
            return got["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable("unexpected chat response shape")


class GeminiChat:
    def __init__(self, model):
        base = live_base("gemini", ENDPOINTS["gemini"]["base"])
        self.key = live_secret(ENDPOINTS["gemini"]["key"])
        if not self.key:
            raise ProviderUnavailable("missing key for gemini")
        self.url = ("%s/v1beta/models/%s:generateContent?key=%s"
                    % (base.rstrip("/"), model, self.key))
        self.model = model

    def chat(self, messages, max_tokens=2048):
        parts = []
        for m in messages:
            for item in (m.get("content") if isinstance(m.get("content"), list)
                         else [{"type": "text", "text": str(m.get("content", ""))}]):
                if item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = (item.get("image_url") or {}).get("url", "")
                    if url.startswith("data:"):
                        header, b64 = url.split(",", 1)
                        mime = header.split(";")[0][5:] or "image/jpeg"
                        parts.append({"inline_data": {"mime_type": mime,
                                                      "data": b64}})
        body = {"contents": [{"parts": parts}],
                "generationConfig": {"maxOutputTokens": max_tokens,
                                     "temperature": 0.2,
                                     "thinkingConfig": {"thinkingLevel": "LOW"}}}
        got = _http_json(self.url, body, {})
        try:
            return "".join(p.get("text", "") for p in
                           got["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise ProviderUnavailable("unexpected gemini response shape")


class AnthropicChat:
    def __init__(self, model):
        base = live_base("anthropic", ENDPOINTS["anthropic"]["base"])
        self.key = live_secret(ENDPOINTS["anthropic"]["key"])
        if not self.key:
            raise ProviderUnavailable("missing key for anthropic")
        self.url = base.rstrip("/") + "/v1/messages"
        self.model = model

    def chat(self, messages, max_tokens=2048):
        conv = []
        for m in messages:
            items = (m.get("content") if isinstance(m.get("content"), list)
                     else [{"type": "text", "text": str(m.get("content", ""))}])
            blocks = []
            for item in items:
                if item.get("type") == "text":
                    blocks.append({"type": "text", "text": item.get("text", "")})
                elif item.get("type") == "image_url":
                    url = (item.get("image_url") or {}).get("url", "")
                    if url.startswith("data:"):
                        header, b64 = url.split(",", 1)
                        mime = header.split(";")[0][5:] or "image/jpeg"
                        blocks.append({"type": "image",
                                       "source": {"type": "base64",
                                                  "media_type": mime,
                                                  "data": b64}})
            conv.append({"role": "user" if m.get("role") != "assistant" else "assistant",
                         "content": blocks})
        body = {"model": self.model, "max_tokens": max_tokens, "messages": conv,
                "output_config": ({} if self.model == "claude-haiku-4-5"
                                  else {"effort": "low"})}
        headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
        got = _http_json(self.url, body, headers)
        try:
            return "".join(b.get("text", "") for b in got["content"]
                           if b.get("type") == "text")
        except (KeyError, TypeError):
            raise ProviderUnavailable("unexpected anthropic response shape")


def make_chat(provider, model):
    native = ENDPOINTS[provider].get("native")
    if native == "gemini":
        return GeminiChat(model)
    if native == "anthropic":
        return AnthropicChat(model)
    return OpenAiChat(provider, model)


def _image_part(jpeg_bytes):
    return {"type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,"
                                + base64.b64encode(jpeg_bytes).decode()}}


class LiveStt:
    """Transcription over configured STT adapters (Active then Fallback)."""

    def __init__(self, adapters):
        self.adapters = adapters  # [(name, kind, model), ...]

    def transcribe(self, creative_key, audio_bytes=None, mime=None,
                   timings_out=None):
        if not audio_bytes:
            raise ProviderUnavailable(
                "no audio for %r: upload media first" % creative_key)
        mime = mime or "audio/wav"

        def call(item):
            name, kind, model, _tier = item
            if kind == "deepgram":
                return self._deepgram(name, model, audio_bytes, mime,
                                      timings_out)
            return self._groq(name, model, audio_bytes, mime, timings_out)

        winner, value = race(
            [a for a in self.adapters if a[3] == "active"],
            [a for a in self.adapters if a[3] == "fallback"], call)
        if not value:
            raise ProviderUnavailable("all STT adapters unavailable")
        return value

    @staticmethod
    def _fill_timings(timings_out, words, level="word"):
        """Append {w, t, end, level} timing entries.

        level is "word" for true word timestamps (Deepgram) or
        "segment" for provider segments (Groq verbose_json): a
        segment's t is the segment start, never a word time, and
        downstream display must say "within X-Ys" rather than
        pretending the word occurred at exactly t.
        """
        if timings_out is None:
            return
        for w in (words or [])[:300]:
            try:
                entry = {
                    "w": str(w.get("word", w.get("text", "")))[:60],
                    "t": round(float(w.get("start", 0)), 2),
                    "level": level}
                if w.get("end") is not None:
                    entry["end"] = round(float(w.get("end")), 2)
                timings_out.append(entry)
            except (TypeError, ValueError):
                continue

    @staticmethod
    def _deepgram(name, model, audio, mime, timings_out=None):
        base = live_base("deepgram", ENDPOINTS["deepgram"]["base"])
        key = live_secret(ENDPOINTS["deepgram"]["key"])
        if not key:
            raise ProviderUnavailable("missing key for deepgram")
        url = base.rstrip("/") + "/v2/listen?model=" + model + "&smart_format=true"
        req = urllib.request.Request(url, data=bytes(audio),
                                     headers={"Authorization": "Token " + key,
                                              "Content-Type": mime},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                got = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable("deepgram HTTP %s" % e.code)
        except OSError as e:
            raise ProviderUnavailable("deepgram unreachable: %s" % e)
        try:
            alt = got["results"]["channels"][0]["alternatives"][0]
            LiveStt._fill_timings(timings_out, alt.get("words"))
            return alt.get("transcript", ""), float(alt.get("confidence", 0.5))
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderUnavailable("unexpected deepgram response shape")

    @staticmethod
    def _groq(name, model, audio, mime, timings_out=None):
        base = live_base("groq-whisper", ENDPOINTS["groq-whisper"]["base"])
        key = live_secret(ENDPOINTS["groq-whisper"]["key"])
        if not key:
            raise ProviderUnavailable("missing key for groq-whisper")
        boundary = "----cilive%d" % abs(hash((name, model)))
        body = b""
        for field, value in (("model", model),
                             ("response_format", "verbose_json")):
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                     % (boundary, field, value)).encode()
        body += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; "
                 "filename=\"audio\"\r\nContent-Type: %s\r\n\r\n"
                 % (boundary, mime)).encode() + bytes(audio) + b"\r\n"
        body += ("--%s--\r\n" % boundary).encode()
        req = urllib.request.Request(
            base.rstrip("/") + "/openai/v1/audio/transcriptions", data=body,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "multipart/form-data; boundary=" + boundary},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                got = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise ProviderUnavailable("groq-whisper HTTP %s" % e.code)
        except OSError as e:
            raise ProviderUnavailable("groq-whisper unreachable: %s" % e)
        if not isinstance(got.get("text"), str):
            raise ProviderUnavailable("unexpected groq-whisper response shape")
        LiveStt._fill_timings(timings_out, got.get("segments"),
                              level="segment")
        return got["text"], 0.7


class LiveVision:
    """Frame annotation over configured vision chat models."""

    MAX_IMAGES = 6

    def __init__(self, roster):
        self.roster = roster  # [(provider, model, tier), ...]

    def sample_frames(self, creative_key, every_s=3.0, duration_s=30.0):
        n = max(1, int(duration_s / every_s))
        return [{"t_sec": round(i * every_s, 1)} for i in range(n)]

    def annotate(self, frames, images=None):
        """Annotate every supplied image, batching at MAX_IMAGES per
        model call. Frames beyond the first batch used to be silently
        dropped (images[:6]), which concentrated analysis on the
        opening seconds and could miss a late CTA/end-frame entirely;
        every batch is now sent and the labels concatenated in time
        order. Any batch failure still fails closed."""
        if not images:
            raise ProviderUnavailable(
                "no frame images: upload creative media first")
        t_all = [f.get("t_sec", 0) for f in frames]
        out = []
        for start in range(0, len(images), self.MAX_IMAGES):
            use = images[start:start + self.MAX_IMAGES]
            t_secs = [(t_all[start + i] if start + i < len(t_all) else 0)
                      for i in range(len(use))]
            out.extend(self._annotate_batch(use, t_secs))
        if not out:
            raise ProviderUnavailable("vision returned no usable frames")
        return out

    def _annotate_batch(self, use, t_secs):
        def call(item):
            provider, model, _tier = item
            client = make_chat(provider, model)
            content = [{"type": "text",
                        "text": VISION_PROMPT % ", ".join(str(t) for t in t_secs)}]
            content += [_image_part(b) for b in use]
            text = client.chat([{"role": "user", "content": content}],
                               max_tokens=cue_cap_tokens(model))
            data = _extract_json(text)
            out = []
            for i, entry in enumerate(data.get("frames", [])):
                if not isinstance(entry, dict):
                    continue
                try:
                    out.append({
                        "t_sec": float(entry.get("t_sec", t_secs[i] if i < len(t_secs) else 0)),
                        "label": str(entry.get("label", "frame"))[:80],
                        "brand_visible": bool(entry.get("brand_visible", False)),
                        "product_visible": bool(entry.get("product_visible", False)),
                        "logo_visible": bool(entry.get("logo_visible", False)),
                        "text_overlay": str(entry.get("text_overlay", ""))[:120],
                        "cta_visible": bool(entry.get("cta_visible", False)),
                        "end_frame": bool(entry.get("end_frame", False)),
                        "cut": bool(entry.get("cut", False)),
                        "confidence": min(1.0, max(0.0, float(
                            entry.get("confidence", 0.5))))})
                except (TypeError, ValueError, IndexError):
                    continue
            if not out:
                raise ProviderUnavailable("vision returned no usable frames")
            return out

        winner, value = race(
            [r for r in self.roster if r[2] == "active"],
            [r for r in self.roster if r[2] == "fallback"], call)
        if not value:
            raise ProviderUnavailable("all vision models unavailable")
        return value


class LiveLlm:
    """Annotation structuring over configured generation models."""

    ASK_PROMPT = (
        "You answer questions about ad-campaign data using ONLY the facts "
        "below. Reply with ONE JSON object: "
        '{"answer": "<2-6 sentences, every claim traceable to the facts>", '
        '"used": ["totals"|"campaigns"|"hooks"|"formats"|"funnel"|'
        '"verticals"|"markets"|"product_timing"|"lengths"|"cta"|'
        '"structure"|"quintiles"|"retention"]}. '
        "If the facts cannot answer, say what data is missing instead of "
        "guessing. Never give generic marketing advice. Facts: %s. "
        "Question: %s")

    def __init__(self, roster):
        self.roster = roster  # [(provider, model, tier), ...]

    def ask_facts(self, question, facts):
        """Raw JSON-text answer over a precomputed fact pack; qa.py validates."""

        def call(item):
            provider, model, _tier = item
            client = make_chat(provider, model)
            text = client.chat(
                [{"role": "user", "content": self.ASK_PROMPT % (
                    json.dumps(facts)[:6000], (question or "")[:500])}],
                max_tokens=min(1024, cue_cap_tokens(model)))
            return text

        _winner, value = race(
            [r for r in self.roster if r[2] == "active"],
            [r for r in self.roster if r[2] == "fallback"], call)
        if not value:
            raise ProviderUnavailable("all ask models unavailable")
        return value

    def structure(self, transcript, labels):
        from .creative import blank_annotation, validate
        prompt = STRUCTURE_PROMPT % (
            (transcript or "")[:4000], json.dumps(labels or [])[:4000])

        def call(item):
            provider, model, _tier = item
            client = make_chat(provider, model)
            params = thinking_params(provider, model)
            _ = params  # vendor reasoning controls ride documented defaults
            text = client.chat([{"role": "user", "content": prompt}],
                               max_tokens=cue_cap_tokens(model))
            data = _extract_json(text)
            ann = blank_annotation()
            for key in ("hook_type", "hook_modality", "hook_confidence",
                        "brand_seconds", "product_seconds", "logo_seconds",
                        "structure", "creator_vs_branded",
                        "creator_confidence", "duration_s",
                        "pace_cuts_per_min"):
                if key in data:
                    ann[key] = data[key]
            errors = validate(ann)
            if errors:
                raise ProviderUnavailable("structurer output invalid: "
                                          + "; ".join(errors[:3]))
            return ann

        winner, value = race(
            [r for r in self.roster if r[2] == "active"],
            [r for r in self.roster if r[2] == "fallback"], call)
        if not value:
            raise ProviderUnavailable("all structuring models unavailable")
        return value


def _configured(provider):
    cfg = ENDPOINTS[provider]
    if cfg["key"] is None:
        return True  # keyless local (ollama)
    if not (live_base(provider, cfg["base"]) if cfg["base"] else
            os.environ.get(_env_base_name(provider))):
        return False
    return bool(live_secret(cfg["key"]))


class LiveBundle:
    """Live provider bundle: real HTTP clients, fail-closed, never mocks.

    Raises ProviderUnavailable unless provider_mode=live AND at least one
    adapter per capability is configured. Media bytes (audio/frames) must
    be supplied by the caller; without them stages raise instead of
    inventing content.
    """

    STT_ROSTER = [
        ("deepgram", "flux-general-en", "active"),
        ("groq-whisper", "whisper-large-v3-turbo", "active"),
        ("deepgram", "nova-3", "fallback"),
        ("groq-whisper", "whisper-large-v3", "fallback"),
    ]
    VISION_ROSTER = [
        ("gemini", "gemini-3.5-flash-lite", "active"),
        ("nvidia", "meta/muse-glimmer-30b", "active"),
        ("openai", "gpt-5.6-luna", "active"),
        ("anthropic", "claude-haiku-4-5", "active"),
        ("zai", "glm-5v-turbo", "active"),
        ("gemini", "gemini-3.7-flash", "fallback"),
        ("openai", "gpt-5.6-sol", "fallback"),
        ("anthropic", "claude-opus-5", "fallback"),
        ("zai", "glm-5.2", "fallback"),
    ]
    LLM_ROSTER = [
        ("deepseek", "deepseek-v4-flash", "active"),
        ("moonshot", "kimi-k2.7-code-highspeed", "active"),
        ("xai", "grok-4.6", "active"),
        ("gemini", "gemini-3.5-flash-lite", "active"),
        ("openai", "gpt-5.6-luna", "active"),
        ("anthropic", "claude-haiku-4-5", "active"),
        ("teamorouter", "deepseek-v4-flash-free", "fallback"),
        ("openrouter", "google/gemini-2.5-flash-lite", "fallback"),
        ("litellm", "(proxy models)", "fallback"),
        ("ollama", "(host models)", "fallback"),
    ]

    def __init__(self):
        if mode() != "live":
            raise ProviderUnavailable("provider_mode != live (mock is active)")
        stt = [(p, m, t) for p, m, t in self.STT_ROSTER if _configured(p)]
        vision = [(p, m, t) for p, m, t in self.VISION_ROSTER
                  if _configured(p)]
        llm = [(p, m, t) for p, m, t in self.LLM_ROSTER if _configured(p)]
        missing = [k for k, v in
                   (("stt", stt), ("vision", vision), ("llm", llm)) if not v]
        if missing:
            raise ProviderUnavailable(
                "no live adapter for: %s (add Keychain keys, keep mock mode "
                "until then)" % ", ".join(missing))
        self.stt = LiveStt([(p, "deepgram" if p == "deepgram" else "groq", m, t)
                            for p, m, t in stt])
        self.vision = LiveVision(vision)
        self.llm = LiveLlm(llm)


class _Unavailable:
    """Fails every stage call with the stored ProviderUnavailable."""

    def __init__(self, err):
        self._err = err

    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise self._err
        return _raise


class Providers:
    def __init__(self):
        self.mode = mode()
        self._live_error = None
        if self.mode == "live":
            try:
                bundle = LiveBundle()
            except ProviderUnavailable as e:
                bundle = None
                self._live_error = e
            if bundle is not None:
                self.stt, self.vision, self.llm = (
                    bundle.stt, bundle.vision, bundle.llm)
            else:
                # Live requested but unconfigured: stages raise, never mock.
                self.stt = self.vision = self.llm = _Unavailable(self._live_error)
        else:
            self.stt = MockStt()
            self.vision = MockVision()
            self.llm = MockLlm()

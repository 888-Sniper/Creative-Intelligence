"""Canonical generation-provider inventory (admin-managed single-active).

Single-active-provider model: exactly one (provider_id, model_id) pair
is active at a time (or nothing is — NULL means paused). Employee
inference never races or falls back across providers; the dispatcher
(``dispatcher.py``) serves ONLY the persisted selection.

Provider set mirrors the Nextly AI catalog
(``apps/mac-backend/src/nextly_backend/providers/catalog.py``,
Nextly ``PROVIDERS`` entries — model id/label pairs below are DATA
copied from that catalog, not code). Excluded from the generation
set, exactly like Nextly's ``LLM_IDS``:

- ``sapling`` (role=detector, not generation),
- ``nextly_trial`` (license-bridge entry, deliberately not selectable).

Two catalog entries are inventoried but UNSUPPORTED (never activatable,
no secret field, no discovery, no chat transport):

- ``chatgpt`` — Nextly's ChatGPT entry reads a local
  ``~/.codex/auth.json`` and impersonates the Codex client against an
  undocumented ``chatgpt.com/backend-api``. Porting that would mean
  shipping credential-scraping plus an unofficial API impersonation;
  this backend refuses to do either.
- ``opencode`` — Nextly's OpenCode entry is driven exclusively through
  a local ``opencode`` CLI subprocess (``providers/opencode.py``:
  ``list_models`` / plan-mode ``run``). There is no safe answer-only
  HTTP transport to adopt, so it stays listed-but-unsupported.

Legacy CI ids map to canonical ids via ALIASES (old Keychain-era
names such as ``moonshot``/``xai``/``zai`` predate the canonical
Nextly spellings ``kimi``/``grok``/``glm``).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

# Shown to employees/admins when no provider is selected (and when a
# live call is attempted while paused). Kept here — a dependency-free
# module — so qa.py, dispatcher.py and the routers share one string.
NOT_CONFIGURED_MESSAGE = (
    "AI is not configured. Contact your administrator.")

# Freshness bar for the offered-model cache (mirrors Nextly + legacy
# CI SYNC_INTERVAL_SECONDS / MODELS_SYNC_TTL_S: 24h).
MODEL_CACHE_TTL_S = 24 * 3600

# Hosts that must never be dialled as a configured base URL, even when
# an operator allowlists them. Loopback stays usable for local
# gateways (Ollama/LiteLLM/stubs); link-local metadata is never a
# legitimate model endpoint.
_SSRF_FORBIDDEN_HOSTS = (
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data",
    "instance-data-compute",
)

#: Extra base-URL hosts an operator explicitly trusts, comma-separated
#: in CREATIVE_INTEL_PROVIDER_BASE_ALLOWLIST (e.g. a LAN LiteLLM
#: proxy). Loopback needs no listing. Anything not loopback-listed
#: here is rejected.
BASE_ALLOWLIST_ENV = "CREATIVE_INTEL_PROVIDER_BASE_ALLOWLIST"


def _loopback(host: str) -> bool:
    if host in ("localhost", "localhost."):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def assert_safe_base_url(base_url: str, *, allowlist: str = "") -> str:
    """Validate an operator-configured base URL (SSRF guard).

    Allows only http/https URLs whose host is loopback or explicitly
    allowlisted via CREATIVE_INTEL_PROVIDER_BASE_ALLOWLIST. Rejects
    credentials in the URL, non-http schemes, and cloud metadata
    endpoints unconditionally. Returns the normalised base (no
    trailing slash). Discovery and chat transports must call this on
    every configured/custom base before dialling; httpx callers must
    additionally pass follow_redirects=False so a validated host
    cannot bounce the request off-allowlist, with TLS verification
    left on.
    """
    import os

    raw = (base_url or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise ValueError("base_url must be an http(s) URL")
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise ValueError("base_url must not embed credentials")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("base_url needs a host")
    if host in _SSRF_FORBIDDEN_HOSTS or host.endswith(
            (".internal", ".metadata.google.internal")):
        raise ValueError("base_url host is forbidden")
    allow = {h.strip().lower().rstrip(".") for h in
             (allowlist or os.environ.get(BASE_ALLOWLIST_ENV, "")
              ).split(",") if h.strip()}
    if not _loopback(host) and host not in allow:
        raise ValueError(
            "base_url host %r is not loopback: add it to %s to allow it"
            % (host, BASE_ALLOWLIST_ENV))
    return raw.rstrip("/")


def _m(*pairs):
    return [{"id": i, "label": lab} for i, lab in pairs]


PROVIDERS = [
    {
        "id": "gemini", "display": "Gemini", "kind": "api_key",
        "supported": True,
        # Discovery mirrors Nextly model_sync.models_url("gemini") +
        # request_headers: GET {base}/v1beta/models with the
        # x-goog-api-key header (probe.py agrees). NOTE the CI chat
        # transport (providers.GeminiChat) instead sends ?key= — both
        # are accepted by Google; discovery keeps the model_sync
        # header scheme verbatim.
        "discovery": {"url": "https://generativelanguage.googleapis.com"
                             "/v1beta/models",
                      "auth": "x-goog-api-key", "shape": "gemini"},
        "chat": {"base": "https://generativelanguage.googleapis.com",
                 "native": "gemini"},
        "keychain": "creative-intel-gemini",
        "models": _m(
            ("gemini-3.8-flash", "Gemini 3.8 Flash"),
            ("gemini-3.7-flash", "Gemini 3.7 Flash"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash"),
            ("gemini-3.5-flash", "Gemini 3.5 Flash"),
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
            ("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
            ("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
            ("gemini-3-flash-preview", "Gemini 3 Flash"),
            ("gemini-2.5-pro", "Gemini 2.5 Pro"),
            ("gemini-2.5-flash", "Gemini 2.5 Flash"),
            ("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
        ),
    },
    {
        "id": "groq", "display": "Groq", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("groq"): fixed OpenAI-compatible root.
        "discovery": {"url": "https://api.groq.com/openai/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.groq.com",
                 "path": "/openai/v1/chat/completions"},
        "keychain": "creative-intel-groq",
        "models": _m(
            ("llama-3.1-8b-instant", "Llama 3.1 8B Instant"),
            ("llama-3.3-70b-versatile", "Llama 3.3 70B"),
            ("openai/gpt-oss-20b", "GPT OSS 20B"),
            ("openai/gpt-oss-120b", "GPT OSS 120B"),
            ("groq/compound-mini", "Groq Compound Mini"),
            ("groq/compound", "Groq Compound"),
            ("qwen/qwen3.8-27b", "Qwen 3.8 27B"),
            ("qwen/qwen3.6-27b", "Qwen 3.6 27B"),
        ),
    },
    {
        "id": "muse", "display": "Meta Muse", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("muse"): {root}/v1/chat/completions with
        # root https://api.meta.ai/v1; models_url mirrors that root.
        "discovery": {"url": "https://api.meta.ai/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.meta.ai",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-muse",
        "models": _m(
            ("muse-spark-1.3", "Muse Spark 1.3"),
            ("muse-spark-1.3-contributor", "Muse Spark 1.3 Contributor"),
            ("muse-spark-1.2", "Muse Spark 1.2"),
            ("muse-spark-1.1", "Muse Spark 1.1"),
            ("muse-spark-1.2-contributor", "Muse Spark 1.2 Contributor"),
        ),
    },
    {
        "id": "openai", "display": "OpenAI", "kind": "api_key",
        "supported": True,
        "discovery": {"url": "https://api.openai.com/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.openai.com",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-openai",
        "models": _m(
            ("gpt-5.6-sol", "GPT 5.6 Sol"),
            ("gpt-5.6-terra", "GPT 5.6 Terra"),
            ("gpt-5.6-luna", "GPT 5.6 Luna"),
            ("gpt-5.5", "GPT 5.5"),
            ("gpt-5.4", "GPT 5.4"),
            ("gpt-5.4-mini", "GPT 5.4 Mini"),
            ("gpt-5.4-nano", "GPT 5.4 Nano"),
        ),
    },
    {
        "id": "anthropic", "display": "Claude", "kind": "api_key",
        "supported": True,
        # Discovery mirrors Nextly request_headers("anthropic"):
        # x-api-key + anthropic-version (same pair the CI native
        # chat transport sends).
        "discovery": {"url": "https://api.anthropic.com/v1/models",
                      "auth": "x-api-key", "shape": "openai"},
        "chat": {"base": "https://api.anthropic.com",
                 "native": "anthropic"},
        "keychain": "creative-intel-anthropic",
        "models": _m(
            ("claude-haiku-4-5", "Claude Haiku 4.5"),
            ("claude-sonnet-5", "Claude Sonnet 5"),
            ("claude-opus-5", "Claude Opus 5"),
            ("claude-fable-5", "Claude Fable 5"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-opus-4-8", "Claude Opus 4.8"),
            ("claude-opus-4-7", "Claude Opus 4.7"),
            ("claude-opus-4-6", "Claude Opus 4.6"),
        ),
    },
    {
        "id": "deepseek", "display": "DeepSeek", "kind": "api_key",
        "supported": True,
        "discovery": {"url": "https://api.deepseek.com/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.deepseek.com",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-deepseek",
        "models": _m(
            ("deepseek-flash", "DeepSeek V4.1 Flash"),
            ("deepseek-v4-flash", "DeepSeek V4 Flash"),
            ("deepseek-v4-pro", "DeepSeek V4 Pro"),
            ("deepseek-v4-flash-vision-exp", "DeepSeek V4 Flash Vision"),
        ),
    },
    {
        "id": "kimi", "display": "Kimi", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("kimi"): {root}/v1/chat/completions with
        # root https://api.moonshot.ai/v1. Shares the legacy moonshot
        # Keychain service (same vendor account).
        "discovery": {"url": "https://api.moonshot.ai/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.moonshot.ai",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-moonshot",
        "models": _m(
            ("kimi-k2.7-code-highspeed", "Kimi K2.7 Code HighSpeed"),
            ("kimi-k2.7-code", "Kimi K2.7 Code"),
            ("kimi-k3", "Kimi K3"),
            ("kimi-k2.6", "Kimi K2.6"),
        ),
    },
    {
        "id": "grok", "display": "Grok", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("grok"): {root}/v1/chat/completions with
        # root https://api.x.ai/v1. Shares the legacy xai Keychain
        # service (same vendor account).
        "discovery": {"url": "https://api.x.ai/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.x.ai",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-xai",
        "models": _m(
            ("grok-4.3", "Grok 4.3"),
            ("grok-4.5", "Grok 4.5"),
            ("grok-4.6", "Grok 4.6"),
            ("grok-4.20-0309-non-reasoning", "Grok 4.20"),
            ("grok-4.20-0309-reasoning", "Grok 4.20 Reasoning"),
            ("grok-build-0.1", "Grok Build"),
        ),
    },
    {
        "id": "qwen", "display": "Qwen", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("qwen"): OpenAI-compatible root
        # dashscope-intl.aliyuncs.com/compatible-mode/v1.
        "discovery": {"url": "https://dashscope-intl.aliyuncs.com"
                             "/compatible-mode/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://dashscope-intl.aliyuncs.com"
                         "/compatible-mode/v1",
                 "path": "/chat/completions"},
        "keychain": "creative-intel-qwen",
        "models": _m(
            ("qwen-turbo", "Qwen Turbo"),
            ("qwen-plus", "Qwen Plus"),
            ("qwen-max", "Qwen Max"),
            ("qwen3.7-plus", "Qwen 3.7 Plus"),
            ("qwen3.8-max", "Qwen 3.8 Max"),
        ),
    },
    {
        "id": "glm", "display": "GLM", "kind": "api_key",
        "supported": True,
        # Nextly _chat_url("glm"): https://api.z.ai/api/paas/v4 root
        # (the legacy CI zai entry still points at open.bigmodel.cn;
        # adoption copies the SECRET only — the default base follows
        # Nextly). Shares the legacy zai Keychain service.
        "discovery": {"url": "https://api.z.ai/api/paas/v4/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.z.ai/api/paas/v4",
                 "path": "/chat/completions"},
        "keychain": "creative-intel-zai",
        "models": _m(
            ("glm-5.3", "GLM 5.3"),
            ("glm-5.3-flash", "GLM 5.3 Flash"),
            ("glm-5.2", "GLM 5.2"),
            ("glm-5.1", "GLM 5.1"),
            ("glm-5-turbo", "GLM 5 Turbo"),
            ("glm-5", "GLM 5"),
            ("glm-4.7-flash", "GLM 4.7 Flash"),
            ("glm-4.7", "GLM 4.7"),
            ("glm-5v-turbo", "GLM 5V Turbo"),
        ),
    },
    {
        "id": "openrouter", "display": "OpenRouter", "kind": "api_key",
        "supported": True,
        # Discovery mirrors Nextly _openrouter_root(base_url):
        # openrouter.ai hosts pin https://openrouter.ai/api/v1, other
        # roots gain /v1. Bearer plus the Nextly app headers.
        "discovery": {"url": "https://openrouter.ai/api/v1/models",
                      "auth": "bearer+app", "shape": "openai"},
        "chat": {"base": "https://openrouter.ai",
                 "path": "/api/v1/chat/completions"},
        "keychain": "creative-intel-openrouter",
        "models": _m(
            ("google/gemini-3.7-flash", "Gemini 3.7 Flash"),
            ("google/gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite"),
            ("google/gemini-2.5-flash", "Gemini 2.5 Flash"),
            ("google/gemini-2.5-pro", "Gemini 2.5 Pro"),
            ("anthropic/claude-sonnet-5", "Claude Sonnet 5"),
            ("anthropic/claude-opus-5", "Claude Opus 5"),
            ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5"),
            ("anthropic/claude-sonnet-4.5", "Claude Sonnet 4.5"),
            ("openai/gpt-5.6-luna", "GPT 5.6 Luna"),
            ("openai/gpt-5.6-sol", "GPT 5.6 Sol"),
            ("openai/gpt-4o-mini", "GPT 4o Mini"),
            ("deepseek/deepseek-chat", "DeepSeek Chat"),
            ("x-ai/grok-4.6", "Grok 4.6"),
            ("moonshotai/kimi-k3", "Kimi K3"),
            ("qwen/qwen3.8-max", "Qwen 3.8 Max"),
            ("z-ai/glm-5.2", "GLM 5.2"),
            ("meta/muse-glimmer-30b", "Muse Glimmer 30B"),
            ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B"),
        ),
    },
    {
        "id": "nvidia", "display": "NVIDIA", "kind": "api_key",
        "supported": True,
        "discovery": {"url": "https://integrate.api.nvidia.com/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://integrate.api.nvidia.com",
                 "path": "/v1/chat/completions"},
        "keychain": "creative-intel-nvidia",
        "models": _m(
            ("meta/muse-glimmer-30b", "Muse Glimmer 30B"),
            ("nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B"),
            ("nvidia/nemotron-3-ultra-550b-a55b", "Nemotron 3 Ultra 550B"),
            ("nvidia/nemotron-nano-3-30b-a3b", "Nemotron Nano 3 30B"),
            ("nvidia/nemotron-3.5-lightning-30b-a3b",
             "Nemotron 3.5 Lightning 30B"),
            ("nvidia/llama-3.1-nemotron-ultra-253b-v1",
             "Llama 3.1 Nemotron Ultra 253B"),
            ("openai/gpt-oss-120b", "GPT OSS 120B"),
            ("openai/gpt-oss-20b", "GPT OSS 20B"),
            ("moonshotai/kimi-k3", "Kimi K3"),
            ("moonshotai/kimi-k2.6", "Kimi K2.6"),
            ("deepseek-ai/deepseek-v4-pro-0813", "DeepSeek V4 Pro"),
            ("deepseek-ai/deepseek-v4-flash-0731", "DeepSeek V4 Flash"),
            ("google/gemma-4-31b-it", "Gemma 4 31B"),
            ("minimaxai/minimax-m3", "MiniMax M3"),
            ("mistralai/mistral-large-2-instruct", "Mistral Large 2"),
        ),
    },
    {
        "id": "teamorouter", "display": "TeamoRouter", "kind": "api_key",
        "supported": True,
        # Nextly models_url("teamorouter"): {root}/v1/models with
        # root https://api.teamorouter.com/v1. No fixed default chat
        # base is assumed here beyond Nextly's (custom roots gain
        # /v1 the same way); operators may override base_url.
        "discovery": {"url": "https://api.teamorouter.com/v1/models",
                      "auth": "bearer", "shape": "openai"},
        "chat": {"base": "https://api.teamorouter.com/v1",
                 "path": "/chat/completions"},
        "keychain": "creative-intel-teamorouter",
        "models": _m(
            ("gemini-3.8-flash", "Gemini 3.8 Flash"),
            ("gemini-3.7-flash", "Gemini 3.7 Flash"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash"),
            ("gemini-3.5-flash", "Gemini 3.5 Flash"),
            ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite"),
            ("gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
            ("deepseek-v4-flash", "DeepSeek V4 Flash"),
            ("deepseek-v4-flash-free", "DeepSeek V4 Flash Free"),
            ("deepseek-v4-pro", "DeepSeek V4 Pro"),
            ("deepseek-v4-pro-free", "DeepSeek V4 Pro Free"),
            ("deepseek-v4-pro-260425", "DeepSeek V4 Pro 260425"),
            ("deepseek-v4-flash-vision-exp", "DeepSeek V4 Flash Vision"),
            ("gpt-5.6-luna", "GPT 5.6 Luna"),
            ("gpt-5.6-terra", "GPT 5.6 Terra"),
            ("gpt-5.6-sol", "GPT 5.6 Sol"),
            ("gpt-5.6-luna-fast", "GPT 5.6 Luna Fast"),
            ("gpt-5.6-terra-fast", "GPT 5.6 Terra Fast"),
            ("gpt-5.6-sol-fast", "GPT 5.6 Sol Fast"),
            ("gpt-5.5", "GPT 5.5"),
            ("gpt-5.5-fast", "GPT 5.5 Fast"),
            ("gpt-5.4", "GPT 5.4"),
            ("gpt-5.4-fast", "GPT 5.4 Fast"),
            ("gpt-5.4-mini", "GPT 5.4 Mini"),
            ("gpt-5.4-mini-fast", "GPT 5.4 Mini Fast"),
            ("claude-haiku-4-5", "Claude Haiku 4.5"),
            ("claude-haiku-4-5-20251001",
             "Claude Haiku 4.5 (2025-10-01)"),
            ("claude-sonnet-5", "Claude Sonnet 5"),
            ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
            ("claude-opus-5", "Claude Opus 5"),
            ("claude-opus-4-8", "Claude Opus 4.8"),
            ("claude-opus-4-7", "Claude Opus 4.7"),
            ("claude-opus-4-6", "Claude Opus 4.6"),
            ("claude-fable-5", "Claude Fable 5"),
            ("claude-fable-5-1", "Claude Fable 5.1"),
            ("kimi-k3", "Kimi K3"),
            ("kimi-k3[1M]", "Kimi K3 1M"),
            ("grok-4.6", "Grok 4.6"),
            ("glm-5.2", "GLM 5.2"),
            ("glm-5.3", "GLM 5.3"),
            ("glm-5.3-flash", "GLM 5.3 Flash"),
            ("glm-5.3-flash-free", "GLM 5.3 Flash Free"),
        ),
    },
    {
        "id": "chatgpt", "display": "ChatGPT (Codex)", "kind": "subscription",
        "supported": False,
        "unsupported_reason": (
            "ChatGPT sign-in reads a local ~/.codex/auth.json and "
            "impersonates the Codex client against an undocumented "
            "chatgpt.com/backend-api. This backend will not scrape "
            "local credentials or ship an unofficial API impersonation, "
            "so ChatGPT can be listed but never tested, refreshed or "
            "activated."),
        # No discovery descriptor: no /models auth exists to mirror.
        "discovery": None,
        "chat": None,
        "keychain": None,
        "models": _m(
            ("gpt-5.6-sol", "GPT 5.6 Sol"),
            ("gpt-5.6-terra", "GPT 5.6 Terra"),
            ("gpt-5.6-luna", "GPT 5.6 Luna"),
            ("gpt-5.5", "GPT 5.5"),
            ("gpt-5.3-codex-spark", "GPT 5.3 Codex Spark"),
        ),
    },
    {
        "id": "ollama", "display": "Ollama", "kind": "local",
        "supported": True,
        # No vendor /models endpoint exists: discovery is the local
        # daemon's GET {base}/api/tags (Nextly ollama.tags_url),
        # keyless. Manual model IDs are validated against the static
        # catalog below plus whatever the daemon reports.
        "discovery": {"url": "http://127.0.0.1:11434/api/tags",
                      "auth": "none", "shape": "ollama-tags"},
        "chat": {"base": "http://127.0.0.1:11434",
                 "path": "/v1/chat/completions"},
        "keychain": None,
        "models": [],
    },
    {
        "id": "litellm", "display": "LiteLLM Proxy", "kind": "gateway",
        "supported": True,
        # OpenAI-compatible gateway: GET {base}/models where base
        # defaults to http://localhost:4000/v1. Keyless when the
        # proxy needs none; Bearer otherwise. No static catalog: the
        # proxy's own list is authoritative, manual IDs allowed.
        "discovery": {"url": "http://localhost:4000/v1/models",
                      "auth": "bearer-or-none", "shape": "openai"},
        "chat": {"base": None, "path": "/v1/chat/completions"},
        "keychain": "creative-intel-litellm",
        "models": [],
    },
    {
        "id": "opencode", "display": "OpenCode", "kind": "local",
        "supported": False,
        "unsupported_reason": (
            "OpenCode is driven only through a local opencode CLI "
            "subprocess (plan-mode agent); no safe answer-only HTTP "
            "transport exists to adopt, so it can be listed but never "
            "tested, refreshed or activated."),
        # No discovery descriptor: the CLI listing is not an HTTP
        # /models endpoint and is never dialled from this backend.
        "discovery": None,
        "chat": None,
        "keychain": None,
        "models": _m(
            ("opencode/muse-spark-1.3-contributor-free",
             "Muse Spark 1.3 (Free)"),
            ("opencode/muse-spark-1.2-contributor-free",
             "Muse Spark 1.2 (Free)"),
            ("opencode/big-pickle", "Big Pickle (Free)"),
            ("opencode/ling-3.0-flash-fin-free", "Ling 3.0 Flash (Free)"),
            ("opencode/mimo-v2.5-free", "Mimo 2.5 (Free)"),
            ("opencode/nemotron-3-ultra-free", "Nemotron 3 Ultra (Free)"),
            ("opencode/nemotron-3.5-lightning-free",
             "Nemotron 3.5 Lightning (Free)"),
        ),
    },
]

BY_ID = {p["id"]: p for p in PROVIDERS}

#: Generation-set ids (everything above except the detector, which is
#: not inventoried at all). Supported + unsupported alike: the admin
#: UI lists unsupported rows with their reason.
GENERATION_IDS = tuple(p["id"] for p in PROVIDERS)

#: Legacy CI provider ids (pre-managed Keychain/race era) mapped to
#: their canonical inventory id. STT-only entries never resolve to a
#: generation provider: groq-whisper/deepgram alias to groq with a
#: capability note instead of a usable mapping.
ALIASES = {
    "zai": "glm",
    "moonshot": "kimi",
    "xai": "grok",
    "muse-glimmer": "nvidia",
    "gpt": "openai",
    "claude": "anthropic",
    "glm-5v": "glm",
    # STT-only: no generation mapping (kept so callers can explain
    # rather than misroute).
    "groq-whisper": "groq",
    "deepgram": None,
}

#: Legacy Keychain services (or env names) the one-time adopt route
#: may copy a secret FROM, per canonical id. Entries list candidate
#: services in priority order; None means keyless/unsupported with
#: nothing to adopt.
ADOPT_SOURCES = {
    "gemini": ["creative-intel-gemini"],
    "groq": ["creative-intel-groq"],
    "muse": ["creative-intel-muse"],
    "openai": ["creative-intel-openai"],
    "anthropic": ["creative-intel-anthropic"],
    "deepseek": ["creative-intel-deepseek"],
    "kimi": ["creative-intel-moonshot"],
    "grok": ["creative-intel-xai"],
    "qwen": ["creative-intel-qwen"],
    "glm": ["creative-intel-zai", "creative-intel-glm"],
    "openrouter": ["creative-intel-openrouter"],
    "nvidia": ["creative-intel-nvidia"],
    "teamorouter": ["creative-intel-teamorouter"],
    "chatgpt": None,
    "ollama": None,
    "litellm": ["creative-intel-litellm"],
    "opencode": None,
}


def resolve(name: str) -> dict | None:
    """Canonical inventory entry for a current or legacy id."""
    if not name:
        return None
    if name in BY_ID:
        return BY_ID[name]
    target = ALIASES.get(name)
    return BY_ID.get(target) if target else None


# ---------------------------------------------------------------------------
# Video-workflow eligibility (item 32).
#
# Actual pipeline inputs (verified in code, not assumed): an uploaded
# video is NEVER sent to any model. video.prepare() decomposes it
# locally with ffmpeg into timed JPEG frames + one 16kHz WAV track
# (sample_times plan); LiveStt transcribes the audio; LiveVision
# annotates the frames as OpenAI-style image_url parts
# (providers._image_part) with per-frame t_sec values; LiveLlm /
# ManagedLlm structures transcript+labels JSON into an annotation
# (pure text). media/thumbnails only decide previews (uploaded image
# > generated SVG > CSS gradient) and never reach inference.
#
# Eligibility rule: a (provider, model) pair is video-workflow
# eligible only when the EXACT model id is verified in the vendor's
# official docs to accept native video input. Image-only support
# does NOT qualify. Levels:
#   "native-video" .. docs list video as an input modality
#   "image"        .. docs list image input but no video input
#   "audio"        .. transcription-only (STT roster)
#   "text-only"    .. chat/text models: refused on the frame path
#   "unverified"   .. no official model-level docs found for the id
#                     (covers future/fictional catalog ids, which must
#                     never be presented as video-capable)
# Checked 2026-09-14 against the doc URLs recorded below.
# ---------------------------------------------------------------------------

VIDEO_SUPPORT_DOCS = {
    "google-gemini": "https://ai.google.dev/gemini-api/docs/models",
    "google-vertex": "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models",
    "anthropic": "https://docs.anthropic.com/en/docs/build-with-claude/vision",
    "openai": "https://platform.openai.com/docs/guides/vision",
    "xai": "https://docs.x.ai/docs/overview",
    "zai-glm-v": "https://docs.z.ai/guides/vlm/glm-4.5v",
    "zai-alibaba": "https://help.aliyun.com/en/model-studio/glm-zhipu",
    "deepgram": "https://developers.deepgram.com/docs/models-overview",
    "groq-stt": "https://console.groq.com/docs/speech-text",
}

#: (provider, model) -> (level, doc-key). Only exact ids listed
#: here carry a verified claim; anything absent is "unverified".
VIDEO_MODEL_SUPPORT = {
    # Google: gemini-2.5-flash + flash-lite list Text/images/video/
    # audio inputs in the official model table (native video OK).
    ("gemini", "gemini-2.5-flash"): ("native-video", "google-gemini"),
    ("gemini", "gemini-2.5-flash-lite"): ("native-video", "google-gemini"),
    ("gemini", "gemini-2.5-pro"): ("native-video", "google-gemini"),
    # Anthropic: all Claude 3/3.5/4 models take image input; Claude
    # takes no video or audio input (image-only -> not eligible).
    ("anthropic", "claude-haiku-4-5"): ("image", "anthropic"),
    ("anthropic", "claude-sonnet-4-5"): ("image", "anthropic"),
    # OpenAI chat completions: image_url vision on GPT-4o-class
    # models; no native video file input (image-only).
    ("openrouter", "openai/gpt-4o-mini"): ("image", "openai"),
    # xAI Grok 4-class: image understanding documented; no native
    # video input documented (image-only).
    ("grok", "grok-4.6"): ("image", "xai"),
    # Zhipu: GLM-4.5V covers image+video understanding; GLM-5.3
    # natively accepts image/video/file. Only these exact ids.
    ("glm", "glm-4.5v"): ("native-video", "zai-glm-v"),
    ("glm", "glm-5.3-flash"): ("native-video", "zai-alibaba"),
    # STT roster (audio only — eligible for the transcribe step,
    # never for frames).
    ("deepgram", "nova-3"): ("audio", "deepgram"),
    ("deepgram", "nova-2"): ("audio", "deepgram"),
    ("deepgram", "nova"): ("audio", "deepgram"),
    ("deepgram", "whisper"): ("audio", "deepgram"),
    ("groq-whisper", "whisper-large-v3-turbo"): ("audio", "groq-stt"),
    ("groq-whisper", "whisper-large-v3"): ("audio", "groq-stt"),
    # Text-only chat models: must never be offered the frame path
    # (vendors document no image input for these API ids; the vision
    # call itself fails closed, and this table lets it fail fast
    # with a named reason instead).
    ("deepseek", "deepseek-v4-flash"): ("text-only", ""),
    ("deepseek", "deepseek-v4-pro"): ("text-only", ""),
    ("deepseek", "deepseek-chat"): ("text-only", ""),
    ("kimi", "kimi-k2.7-code-highspeed"): ("text-only", ""),
    ("kimi", "kimi-k3"): ("text-only", ""),
    ("groq", "llama-3.1-8b-instant"): ("text-only", ""),
    ("groq", "llama-3.3-70b-versatile"): ("text-only", ""),
}


def frame_support(provider_id: str, model_id: str) -> tuple:
    """(level, doc-url) for sending video frames to a model.

    Unknown ids return ("unverified", ""): callers proceed only
    where they already fail closed per-call, and must never label
    them video-capable in the UI.
    """
    hit = VIDEO_MODEL_SUPPORT.get((provider_id or "", model_id or ""))
    if hit is None:
        return ("unverified", "")
    level, doc_key = hit
    return (level, VIDEO_SUPPORT_DOCS.get(doc_key, ""))


def video_eligible(provider_id: str, model_id: str) -> bool:
    """True only for exact ids verified native-video capable."""
    return frame_support(provider_id, model_id)[0] == "native-video"

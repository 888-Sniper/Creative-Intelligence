"""Admin-managed single-active LLM dispatcher.

Unlike providers.LiveLlm (which races Active/Fallback rosters across
many vendors), ManagedLlm serves EXACTLY the persisted
active_provider_selection row — one provider, one exact model:

- No selection (missing row or NULL ids) -> ProviderUnavailable with
  NOT_CONFIGURED_MESSAGE (honest "contact your administrator",
  never legacy race, never mocks in live mode).
- Selection model must match the offered-model cache EXACTLY
  (no fuzzy match) and the cache entry must be fresh (24h TTL); a
  stale/missing cache errors and asks for a refresh — never
  auto-substitutes another model.
- The chat client is built via providers.make_chat on the SELECTED
  provider only, with the DB-decrypted secret (legacy Keychain/env
  values enter ONLY through the explicit adopt route, never
  implicitly). Exactly ONE attempt: no race(), no fallback, no retry
  across providers. At most one sequential same-selection retry, and
  only for safe network-level errors (unreachable/timeout — never
  for HTTP responses or bad model output, which could double-bill).
- Provider errors propagate with the provider id plus retry guidance
  (marked "[provider=<id>]") so routes can map them to 502 while the
  not-configured message keeps its 409.

Discovery (test/refresh) mirrors Nextly model_sync.py header/URL
schemes (request_headers / models_url) and probe.py endpoint
constants; merge mirrors merge_models (live discovery intersected
with the static inventory filter, static labels win). Where a
provider has no discovery endpoint (chatgpt/opencode: unsupported —
no entry here at all), the inventory static catalog plus validated
manual-ID entry is the only path, and activate() enforces it.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from creative_intel import provider_inventory as inv
from creative_intel import providers as providers_mod

NOT_CONFIGURED_MESSAGE = inv.NOT_CONFIGURED_MESSAGE
CACHE_TTL_S = inv.MODEL_CACHE_TTL_S

# Total budget for one discovery HTTP call (headers AND body
# read+parse). httpx gets connect/read/write caps inside it; the
# deadline check below enforces the total even if a fake server
# dribbles bytes.
DISCOVERY_TIMEOUT_S = 10.0

#: Failure substrings from providers._http_json that mean "the bytes
#: never got there" (safe to send once more). HTTP-status failures
#: and bad-payload failures are NOT retried: the vendor already did
#: (or refused) the work.
_NETWORK_FAILURE_MARKERS = ("unreachable", "timed out", "timeout")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fresh_enough(fetched_at: str, now: float | None = None) -> bool:
    try:
        ts = datetime.fromisoformat((fetched_at or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() < CACHE_TTL_S


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def has_selection(db_path: str) -> bool:
    """True when a persisted (provider, model) selection exists.

    False on paused (missing row / NULL ids) AND on any read error
    (e.g. pre-migration DB): callers keep legacy behaviour rather
    than failing boot on old databases. Raises nothing.
    """
    try:
        with _connect(db_path) as conn:
            if "active_provider_selection" not in _tables(conn):
                return False
            row = conn.execute(
                "SELECT provider_id, model_id FROM "
                "active_provider_selection WHERE id = 1").fetchone()
            return bool(row and row["provider_id"] and row["model_id"])
    except Exception:
        return False


def load_selection(conn: sqlite3.Connection) -> dict | None:
    """The singleton selection row, or None when paused."""
    row = conn.execute(
        "SELECT provider_id, model_id, revision, updated_by, updated_at"
        " FROM active_provider_selection WHERE id = 1").fetchone()
    if row is None or not row["provider_id"] or not row["model_id"]:
        return None
    return dict(row)


def load_config(conn: sqlite3.Connection, provider_id: str) -> dict | None:
    row = conn.execute(
        "SELECT provider_id, display, kind, base_url, secret_enc,"
        " secret_updated_at, created_at, updated_at"
        " FROM provider_configs WHERE provider_id = ?", (provider_id,)).fetchone()
    return dict(row) if row is not None else None


def cache_rows(conn: sqlite3.Connection, provider_id: str) -> list:
    return [dict(r) for r in conn.execute(
        "SELECT provider_id, model_id, display, offered, fetched_at"
        " FROM provider_model_cache WHERE provider_id = ?",
        (provider_id,))]


# ---------------------------------------------------------------------------
# Discovery (mirrors Nextly model_sync.py / probe.py)
# ---------------------------------------------------------------------------

_OPENROUTER_APP_HEADERS = {
    "HTTP-Referer": "https://nextly.ai",
    "X-Title": "Nextly AI",
}

# Non-generation token fragments: live ids containing one are not
# offered chat models (mirrors Nextly SKIP_TOKENS).
_SKIP_TOKENS = (
    "whisper", "tts", "embed", "dall", "imagine", "imagen", "image",
    "video", "veo", "omni", "audio", "voice", "moderation",
    "transcribe", "canary", "asr", "realtime", "sora", "flux",
    "lyria", "aqa", "computer-use", "text-embedding",
)


def is_offered_model(provider_id: str, model_id: str) -> bool:
    """Static per-provider filter mirroring Nextly is_offered_model."""
    ident = (model_id or "").lower()
    if any(tok in ident for tok in _SKIP_TOKENS):
        return False
    if provider_id == "gemini":
        return ident.startswith("gemini-")
    if provider_id == "openai":
        return ident.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))
    if provider_id == "anthropic":
        return "claude" in ident
    if provider_id == "deepseek":
        return "deepseek" in ident
    if provider_id == "kimi":
        return ident.startswith(("kimi-", "moonshot-"))
    if provider_id == "grok":
        return ident.startswith("grok-")
    if provider_id == "muse":
        return ident.startswith("muse-")
    if provider_id == "qwen":
        return "qwen" in ident
    if provider_id == "glm":
        return ident.startswith("glm-")
    if provider_id == "groq":
        return True
    if provider_id == "teamorouter":
        return (ident.startswith(
            ("gpt-", "o1", "o3", "o4", "chatgpt-", "gemini-", "kimi-",
             "moonshot-", "grok-", "glm-"))
            or "claude" in ident
            or "deepseek" in ident
            or "qwen" in ident)
    if provider_id in ("openrouter", "nvidia"):
        if ident.endswith(":batch") or ident.endswith("/batch"):
            return False
        return "/" in ident or ident.startswith("~")
    if provider_id in ("ollama", "litellm"):
        return True
    return False


def discovery_headers(provider_id: str, secret: str | None) -> dict:
    """Auth headers mirroring Nextly request_headers (+probe shapes)."""
    if provider_id == "anthropic":
        return {"x-api-key": secret or "",
                "anthropic-version": "2023-06-01"}
    if provider_id == "gemini":
        # model_sync fetch_model_ids("gemini") header scheme.
        return {"x-goog-api-key": secret or ""} if (secret or "") else {}
    if provider_id in ("ollama",):
        return {}
    if provider_id == "litellm" and not (secret or "").strip():
        return {}
    headers = {"Authorization": "Bearer %s" % (secret or "")}
    if provider_id == "openrouter":
        headers.update(_OPENROUTER_APP_HEADERS)
    return headers


def _models_suffix(provider_id: str) -> str:
    if provider_id == "ollama":
        return "/api/tags"
    if provider_id == "gemini":
        return "/v1beta/models"
    return "/models"


def discovery_url(provider_id: str, base_url: str | None = None) -> str | None:
    """Discovery URL mirroring Nextly models_url (+ollama tags_url).

    None when the provider has no discovery endpoint (unsupported
    entries never reach here — callers reject them first).
    """
    spec = inv.BY_ID.get(provider_id)
    if spec is None or not spec.get("discovery"):
        return None
    default = spec["discovery"]["url"]
    if not base_url:
        return default
    root = inv.assert_safe_base_url(base_url)
    if provider_id == "ollama":
        # Mirrors Nextly ollama.tags_url: strip /v1 or /api tails.
        if root.endswith("/v1"):
            root = root[:-len("/v1")]
        if root.endswith("/api"):
            root = root[:-len("/api")]
        return root + "/api/tags"
    if provider_id == "litellm":
        return root if root.endswith("/models") else root + "/models"
    if provider_id == "gemini":
        return root.rstrip("/") + "/v1beta/models"
    if provider_id == "openrouter" and "openrouter.ai" in root:
        return "https://openrouter.ai/api/v1/models"
    # Mirrors Nextly per-vendor root logic: a root already ending in
    # /v1 takes /models, otherwise /v1/models.
    if root.endswith("/v1"):
        return root + "/models"
    return root + "/v1/models"


def _extract_ids(provider_id: str, payload) -> list:
    """Model ids from a discovery payload (mirrors extract_ids)."""
    spec = inv.BY_ID.get(provider_id) or {}
    shape = (spec.get("discovery") or {}).get("shape", "openai")
    items: list = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if shape in ("gemini",):
            items = payload.get("models") or []
        elif shape == "ollama-tags":
            items = payload.get("models") or []
        else:
            items = (payload.get("data") or payload.get("models")
                     or payload.get("items") or [])
    ids: list = []
    seen: set = set()
    for item in items if isinstance(items, list) else []:
        value = None
        if isinstance(item, str):
            value = item
        elif isinstance(item, dict):
            cand = item.get("id") or item.get("name")
            value = str(cand) if cand else None
        if not value:
            continue
        model_id = value.removeprefix("models/").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        ids.append(model_id)
    return ids


def humanize_model(model_id: str, brand: str = "") -> str:
    """Display label fallback mirroring Nextly humanize_model."""
    text = model_id.split("/")[-1].replace("_", "-")
    acronyms = {"gpt": "GPT", "glm": "GLM", "llm": "LLM", "oss": "OSS",
                "vl": "VL", "api": "API", "tts": "TTS", "stt": "STT"}
    parts: list = []
    for part in text.split("-"):
        if not part:
            continue
        low = part.lower()
        if low in acronyms:
            parts.append(acronyms[low])
        elif len(part) > 1 and part[1:].replace(".", "").isdigit():
            parts.append(part)
        else:
            parts.append(part[:1].upper() + part[1:])
    label = " ".join(parts) or model_id
    if brand and not label.lower().startswith(brand.lower()):
        return "%s %s" % (brand, label)
    return label


def merge_with_static(provider_id: str, live_ids: list) -> list:
    """Catalog merge mirroring Nextly merge_models.

    live discovery intersected with the static offered filter; static
    entries present live keep their documented labels first, brand-new
    live ids append with humanized labels. Empty live set -> [] (a
    successful fetch offering nothing must never present stale static
    assumptions as live).
    """
    spec = inv.BY_ID.get(provider_id) or {}
    catalog = list(spec.get("models") or [])
    live = {m for m in live_ids if is_offered_model(provider_id, m)}
    if not live:
        return []
    labels = {str(m["id"]): str(m["label"]) for m in catalog if m.get("id")}
    merged: list = []
    seen: set = set()
    for item in catalog:
        mid = str(item.get("id") or "")
        if mid and mid in live and mid not in seen:
            merged.append({"id": mid,
                           "label": labels.get(mid) or humanize_model(
                               mid, brand=str(spec.get("display") or ""))})
            seen.add(mid)
    for mid in live_ids:
        if mid in live and mid not in seen:
            merged.append({"id": mid, "label": humanize_model(
                mid, brand=str(spec.get("display") or ""))})
            seen.add(mid)
    return merged


def fetch_model_ids(provider_id: str, secret: str | None,
                     base_url: str | None = None,
                     timeout_s: float = DISCOVERY_TIMEOUT_S) -> list | None:
    """Live discovery ids, or None on ANY failure (callers preserve).

    One bounded GET (total timeout covers headers AND body read+parse;
    no redirects — a 3xx is a failure, never followed off-allowlist;
    TLS verification stays on). Secret travels only in headers.
    """
    import httpx

    url = discovery_url(provider_id, base_url)
    if url is None:
        return None
    if not (secret or "").strip() and provider_id not in ("ollama", "litellm"):
        return None
    headers = discovery_headers(provider_id, secret)
    deadline = time.monotonic() + timeout_s
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=5.0),
                          follow_redirects=False, verify=True) as http:
            resp = http.get(url, headers=headers)
            if time.monotonic() > deadline:
                return None
            if resp.status_code != 200:
                return None
            try:
                payload = resp.json()
            except ValueError:
                return None
            if time.monotonic() > deadline:
                return None
            if isinstance(payload, dict) and not any(
                    isinstance(payload.get(k), list)
                    for k in ("data", "models", "items")):
                return None
            ids = _extract_ids(provider_id, payload)
            seen: set = set()
            return [m for m in ids if not (m in seen or seen.add(m))]
    except Exception:
        return None


def probe_provider(provider_id: str, secret: str | None,
                    base_url: str | None = None) -> tuple:
    """Validate credentials: (offered models, latency_ms).

    Raises ValueError for bad input (unknown/unsupported id, unsafe
    base) and ProviderUnavailable for transport/discovery failure —
    never echoes the secret.
    """
    spec = inv.BY_ID.get(provider_id)
    if spec is None:
        raise ValueError("unknown provider %r" % (provider_id,))
    if not spec.get("supported"):
        raise ValueError("%s is listed but unsupported: %s"
                         % (provider_id,
                            spec.get("unsupported_reason", "")))
    if base_url:
        inv.assert_safe_base_url(base_url)
    start = time.monotonic()
    live = fetch_model_ids(provider_id, secret, base_url)
    latency_ms = int((time.monotonic() - start) * 1000)
    if live is None:
        raise providers_mod.ProviderUnavailable(
            "validation failed for %s: discovery unreachable or key "
            "rejected [provider=%s] Retry: confirm the key and base URL,"
            " then test again." % (provider_id, provider_id))
    offered = merge_with_static(provider_id, live)
    return offered, latency_ms


# ---------------------------------------------------------------------------
# Managed LLM
# ---------------------------------------------------------------------------

def _error(provider_id: str, message: str) -> providers_mod.ProviderUnavailable:
    return providers_mod.ProviderUnavailable(
        "%s [provider=%s] Retry: refresh the catalog, confirm the "
        "active model, then retry once; contact your administrator if "
        "it persists." % (message, provider_id))


class ManagedLlm:
    """LiveLlm-compatible structuring/answering over the selection.

    Same validation/output contracts as providers.LiveLlm (same
    prompts, same _extract_json, same blank_annotation/validate, same
    ASK_PROMPT) — but exactly one provider, one exact model, one
    attempt. ``managed = True`` tells qa.answer to surface failures
    instead of falling back to rules.
    """

    managed = True
    ASK_PROMPT = providers_mod.LiveLlm.ASK_PROMPT

    def __init__(self, db_path: str | None = None, conn=None):
        if db_path is None and conn is None:
            raise ValueError("ManagedLlm needs db_path or conn")
        self._db_path = db_path
        self._conn = conn

    def _selected(self) -> tuple:
        """(provider_id, model_id, secret, base_url) or raise."""
        if self._conn is not None:
            return _resolve(self._conn)
        with _connect(self._db_path) as conn:
            return _resolve(conn)

    def _client(self):
        provider_id, model_id, secret, base_url = self._selected()
        keyless = provider_id == "ollama" or (
            provider_id == "litellm" and not (secret or ""))
        try:
            return providers_mod.make_chat(
                provider_id, model_id, secret=(secret if secret else ""),
                base_url=base_url, keyless=keyless)
        except providers_mod.ProviderUnavailable as exc:
            raise _error(provider_id, str(exc))

    def _once(self, fn):
        """One attempt plus at most one same-selection retry for safe
        network errors only (unreachable/timeout). Every failure
        leaves here marked with the provider id plus retry guidance.
        """
        provider_id, model_id, _secret, _base = self._selected()
        client = self._client()
        try:
            return fn(client, provider_id, model_id)
        except providers_mod.ProviderUnavailable as exc:
            text = str(exc).lower()
            if "[provider=" in text:
                raise
            if not any(mark in text
                       for mark in _NETWORK_FAILURE_MARKERS):
                raise _error(provider_id, str(exc))
            try:
                return fn(self._client(), provider_id, model_id)
            except providers_mod.ProviderUnavailable as exc2:
                raise _error(provider_id, str(exc2))

    def ask_facts(self, question, facts):
        """Raw JSON-text answer; qa.py validates (LiveLlm contract)."""
        def _call(client, _provider_id, model_id):
            return client.chat(
                [{"role": "user", "content": self.ASK_PROMPT % (
                    json.dumps(facts)[:6000], (question or "")[:500])}],
                max_tokens=min(1024,
                               providers_mod.cue_cap_tokens(model_id)))
        return self._once(_call)

    def structure(self, transcript, labels):
        """Annotation structuring (LiveLlm.structure contract)."""
        from creative_intel.creative import blank_annotation, validate

        prompt = providers_mod.STRUCTURE_PROMPT % (
            (transcript or "")[:4000], json.dumps(labels or [])[:4000])

        def _call(client, provider_id, model_id):
            params = providers_mod.thinking_params(provider_id, model_id)
            _ = params  # vendor reasoning rides documented defaults
            text = client.chat([{"role": "user", "content": prompt}],
                               max_tokens=providers_mod.cue_cap_tokens(
                                   model_id))
            data = providers_mod._extract_json(text)
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
                raise providers_mod.ProviderUnavailable(
                    "structurer output invalid: " + "; ".join(errors[:3]))
            return ann

        return self._once(_call)


def _resolve(conn: sqlite3.Connection) -> tuple:
    """Resolve the live selection to dial credentials (one transaction).

    Raises ProviderUnavailable (fail-closed): paused, unknown/
    unsupported provider, model mismatch vs the offered cache, stale
    cache, missing secret, or undecryptable secret. Exact-model-only:
    the selection model must equal a cached offered model id byte for
    byte — never a prefix/fuzzy match, never an auto-substitute.
    """
    sel = load_selection(conn)
    if sel is None:
        raise providers_mod.ProviderUnavailable(NOT_CONFIGURED_MESSAGE)
    provider_id, model_id = sel["provider_id"], sel["model_id"]
    spec = inv.BY_ID.get(provider_id)
    if spec is None:
        raise _error(provider_id, "unknown provider %r" % (provider_id,))
    if not spec.get("supported"):
        raise _error(provider_id, "%s is unsupported: %s"
                     % (provider_id, spec.get("unsupported_reason", "")))
    rows = cache_rows(conn, provider_id)
    match = next((r for r in rows
                  if r["model_id"] == model_id and r["offered"]), None)
    if match is None:
        raise _error(
            provider_id,
            "model %r is not in the offered catalog for %s: refresh the"
            " catalog and re-activate an offered model"
            % (model_id, provider_id))
    if not _fresh_enough(match["fetched_at"]):
        raise _error(
            provider_id,
            "model catalog for %s is stale (older than 24h): refresh it"
            " before inference" % provider_id)
    cfg = load_config(conn, provider_id)
    secret = None
    if cfg is not None and cfg.get("secret_enc"):
        from ci_backend import token_crypto
        try:
            secret = token_crypto.decrypt_secret(cfg["secret_enc"])
        except Exception as exc:
            raise _error(
                provider_id,
                "stored secret for %s is undecryptable (master key"
                " mismatch): re-save it in provider settings"
                % provider_id) from exc
    needs_key = providers_mod.ENDPOINTS.get(provider_id, {}).get("key")
    if needs_key and not secret and not (
            provider_id == "litellm"):
        raise _error(provider_id, "no secret stored for %s: save one in"
                     " provider settings" % provider_id)
    base_url = (cfg.get("base_url") if cfg else None) or None
    if base_url:
        try:
            inv.assert_safe_base_url(base_url)
        except ValueError as exc:
            raise _error(provider_id, "unsafe base_url: %s" % exc)
    return provider_id, model_id, secret, base_url

# Providers

Ported from Nextly AI (`docs/PROVIDERS.md`, verified 26 August 2026).
Live clients are wired in `Backend/creative_intel/providers.py`
(stdlib urllib, OpenAI-compatible chat plus native Gemini/Anthropic,
Deepgram + Groq STT). No secrets live in this repo; every key lives
in macOS Keychain under the service name listed, with
`CREATIVE_INTEL_KEY_*` env overrides for CI/non-macOS and
`CREATIVE_INTEL_BASE_*` endpoint overrides for stubs/proxies.
Live stages need uploaded media bytes (audio/frames); without them
they raise instead of inventing content.

## Pattern (same as Nextly)

- **Mock default.** Mock implementations are first-class in mock mode
  only. Live with missing keys stays unavailable; it never silently
  falls back to mocks.
- **Active/Fallback race.** Race the Active roster, first token wins.
  If the Active set stalls (`fallback_timeout_s`), errors, or returns
  empty, race the Fallback roster into the same slot.
- **Daily models sync.** Each saved key is re-checked against that
  provider's `/models` endpoint when the last check is older than
  24 hours. New chat ids are added; vanished ones leave the rosters.
  Sync state lives in `~/.cache/creative-intel/`, never in the repo.
- **Keychain configured/missing.** Presence is probed with
  `security find-generic-password -s <service> -w`; values are never
  read into logs. Status is `mock` | `configured` | `missing`.
- **Cue caps.** `max_tokens` 2048 default; 1024 for ids that do not
  think unless asked (`gpt-4o*`, `deepseek-chat`, `llama-3*`,
  `gemini-2.5-flash-lite`, Claude 3 / Haiku-4 / Sonnet-4 / Opus-4).
- **Thinking handling.** Reasoning traces never reach the cue:
  DeepSeek Active disables thinking, Fallback uses
  `reasoning_effort=low`; OpenRouter sends
  `reasoning: {"effort": "low", "exclude": true}`; Claude pins
  `output_config: {"effort": "low"}` (Haiku 4.5 excluded);
  Gemini 3.x uses `thinkingLevel: LOW`.

## Transcription

| Provider | Active | Fallback | Keychain service |
|---|---|---|---|
| Deepgram | `flux-general-en` (`/v2/listen`) | `nova-3` replay | `creative-intel-deepgram` |
| Groq Whisper | `whisper-large-v3-turbo` | `whisper-large-v3` | `creative-intel-groq-stt` |

Nextly thresholds mirrored: `eot_threshold=0.7`,
`eager_eot_threshold=0.4`, `eot_timeout_ms=3200`.

## Vision (creative frames)

| Provider | Active | Fallback | Keychain service |
|---|---|---|---|
| Gemini | `gemini-3.5-flash-lite` | `gemini-3.7-flash` | `creative-intel-gemini` |
| Muse Glimmer (NVIDIA) | `meta/muse-glimmer-30b` | `meta/muse-glimmer-30b` | `creative-intel-nvidia` |
| GPT | `gpt-5.6-luna` | `gpt-5.6-sol` | `creative-intel-openai` |
| Claude | `claude-haiku-4-5` | `claude-opus-5` | `creative-intel-anthropic` |
| GLM | `glm-5v-turbo` | `glm-5.2` | `creative-intel-zai` |

## Generation (copy + insights)

| Provider | Active | Fallback | Keychain service |
|---|---|---|---|
| DeepSeek | `deepseek-v4-flash` | `deepseek-v4-pro` | `creative-intel-deepseek` |
| Kimi | `kimi-k2.7-code-highspeed` | `kimi-k3` | `creative-intel-moonshot` |
| Grok | `grok-4.6` | `grok-4.6` | `creative-intel-xai` |
| Gemini | `gemini-3.5-flash-lite` | `gemini-3.7-flash` | `creative-intel-gemini` |
| GPT | `gpt-5.6-luna` | `gpt-5.6-sol` | `creative-intel-openai` |
| Claude | `claude-haiku-4-5` | `claude-opus-5` | `creative-intel-anthropic` |
| TeamoRouter | `deepseek-v4-flash-free` | `deepseek-v4-pro-free` | `creative-intel-teamorouter` |
| OpenRouter | `google/gemini-2.5-flash-lite` | `anthropic/claude-sonnet-4.5` | `creative-intel-openrouter` |
| Ollama (local) | host models | host models | none (`http://127.0.0.1:11434`) |
| LiteLLM (gateway) | proxy models | proxy models | `creative-intel-litellm` |

## Grounded Q&A

Answers are grounded **only** in uploaded data. Every cited fact
carries a source-priority label: Uploaded CSV > Annotation >
ASR Transcript > Benchmark Derived. Each answer opens a pending
review; the one-pager export is gated until reviews reach zero.

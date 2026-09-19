# Jev Decision Client

Jev (TypeSafe System One) evaluates typed questions (choice / score /
noul) against a state string and returns structured answers with
probabilities and confidence for code to branch on. It is not a chat
LLM: use it for automation gut-checks, never for free-text generation.

- Client: `Backend/creative_intel/jev.py` (stdlib only, no new
  dependencies). Tests: `tests/test_jev.py` (urlopen stubbed; live
  network is never touched by tests).
- Endpoint: `POST https://api.typesafe.ai/v1/systemone`,
  `Authorization: Bearer <key>`, model `jev-latest`.
- Key: `TYPESAFE_API_KEY` environment variable (local `.env`,
  gitignored) — never in source, logs, or Git. Synthetic data only
  until a real use case is approved.
- Verified live with synthetic probes (typed Noul + Choice round-trip).

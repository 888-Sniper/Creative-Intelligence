"""Jev (TypeSafe System One) decision client.

Jev is not a chat LLM: it evaluates typed questions (choice / score /
noul) against a state string and returns structured answers with
probabilities and confidence that code can branch on. Use it for
automation gut-checks (route this, flag that, accept or escalate),
never for free-text generation.

Network shape (verified against the live API):
    POST https://api.typesafe.ai/v1/systemone
    Authorization: Bearer <key>
    {"state": str, "model": "jev-latest", "questions": {...}}

The key comes from the TYPESAFE_API_KEY environment variable (local
.env, gitignored) — never in source, logs, or Git. Stdlib only
(urllib): no new dependencies.
"""

import json
import os
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
ENV_VAR = "TYPESAFE_API_KEY"
TIMEOUT_S = 30


class JevError(Exception):
    """A Jev call failed: transport, auth, or malformed response."""


def system_one(state, questions, api_key=None, model=DEFAULT_MODEL,
               timeout_s=TIMEOUT_S):
    """Evaluate typed questions against state; returns the answers map.

    api_key defaults to the TYPESAFE_API_KEY environment variable.
    Raises JevError on empty inputs, HTTP failures (including 401/403
    for a bad key), timeouts, and non-JSON or answer-less responses.
    The key is never logged; only its absence is reported.
    """
    key = (api_key if api_key is not None
           else os.environ.get(ENV_VAR, ""))
    if not isinstance(state, str) or not state.strip():
        raise JevError("jev needs a non-empty state string")
    if not isinstance(questions, dict) or not questions:
        raise JevError("jev needs at least one question")
    if not key or not key.strip():
        raise JevError("jev needs an API key (TYPESAFE_API_KEY)")
    payload = json.dumps({"state": state, "model": model or DEFAULT_MODEL,
                          "questions": questions}).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key.strip()})
    try:
        with urllib.request.urlopen(request,
                                    timeout=timeout_s) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise JevError("jev refused the call (HTTP %s)" % exc.code)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise JevError("jev unreachable: %s" % exc)
    try:
        decoded = json.loads(body)
    except ValueError:
        raise JevError("jev returned non-JSON")
    if not isinstance(decoded, dict) or not isinstance(
            decoded.get("answers"), dict):
        raise JevError("jev returned no answers map")
    return decoded["answers"]

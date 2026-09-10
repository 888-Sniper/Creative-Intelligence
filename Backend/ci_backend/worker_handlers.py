"""Job handlers for the persistent worker (P0).

Each handler runs blocking provider work OUTSIDE the FastAPI event
loop — either in the standalone worker service or, when no worker
claims the job, inline inside the request's bounded executor thread
(via jobs.run_through). Handlers only ever return JSON-safe dicts.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from creative_intel import (  # noqa: E402
    benchmarks,
    qa,  # noqa: E402
)
from creative_intel import providers as providers_mod

from ci_backend import actions as legacy  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def _providers():
    return providers_mod.Providers()


def run_pipeline(conn, payload, owner, ctx):
    settings = ctx.get("settings") or Settings()
    _ = settings
    result = legacy.apply_action(
        conn, "pipeline", dict(payload or {}), _providers(),
        media_dir=ctx.get("media_dir"), actor=owner or "")
    if not isinstance(result, dict):
        return {"result": result}
    return result


def run_ask(conn, payload, owner, ctx):
    _ = owner
    payload = dict(payload or {})
    prov = _providers()
    live = prov.llm if getattr(prov, "mode", "mock") == "live" else None
    scope = benchmarks.Scope.from_payload(payload)
    result = qa.answer(conn, payload.get("question", ""), llm=live,
                       scope=scope)
    if not isinstance(result, dict):
        return {"answer": result}
    return result


HANDLERS = {
    "pipeline": run_pipeline,
    "ask": run_ask,
}


def run(conn, kind, payload, owner, ctx, job_id):
    _ = job_id
    try:
        handler = HANDLERS[kind]
    except KeyError:
        raise ValueError("unknown job kind %r" % (kind,))
    return handler(conn, payload, owner, ctx or {})

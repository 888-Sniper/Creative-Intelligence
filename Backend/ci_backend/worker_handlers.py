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
    analyst_chat,  # noqa: E402
    benchmarks,
    qa,  # noqa: E402
)
from creative_intel import jobs as jobs_mod
from creative_intel import providers as providers_mod

from ci_backend import actions as legacy  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def _db_path(ctx, conn):
    """Identity sqlite path for the managed LLM (same file as conn).

    The product connection's own database file (PRAGMA database_list)
    is authoritative — it is the same sqlite file as the identity
    tables by construction (deps.bind_database). ctx settings are
    only a fallback (their configured path can differ from the bound
    file, e.g. in tests).
    """
    try:
        for _seq, _name, path in conn.execute("PRAGMA database_list"):
            if _name == "main" and path:
                return str(path)
    except Exception:
        pass
    try:
        settings = (ctx or {}).get("settings")
        path = getattr(settings, "database_path", None)
        if path:
            return str(path)
    except Exception:
        pass
    return None


def _providers(ctx=None, conn=None):
    return providers_mod.Providers(db_path=_db_path(ctx, conn)
                                   if conn is not None else None)


def _control(conn, job_id):
    """(progress, cancelled) bound to one job row.

    cancelled() re-reads the row: True once the owner/admin marks it
    cancelled (or the row vanishes). Progress writes are best-effort —
    a finished row simply stops accepting them.
    """
    def progress(pct, _stage=""):
        try:
            jobs_mod.set_progress(conn, job_id, pct)
        except Exception:
            pass

    def cancelled():
        try:
            row = jobs_mod.get(conn, job_id)
        except Exception:
            return False
        return row is None or row["status"] == "cancelled"

    return progress, cancelled


def _raise_if_cancelled(cancelled):
    if cancelled is not None and cancelled():
        raise jobs_mod.JobCancelled("job cancelled before start")


def run_pipeline(conn, payload, owner, ctx, job_id=None):
    settings = ctx.get("settings") or Settings()
    _ = settings
    progress, cancelled = (None, None)
    if job_id:
        progress, cancelled = _control(conn, job_id)
        progress(5, "start")
        _raise_if_cancelled(cancelled)
    result = legacy.apply_action(
        conn, "pipeline", dict(payload or {}), _providers(ctx, conn),
        media_dir=ctx.get("media_dir"), actor=owner or "",
        progress=progress, cancelled=cancelled)
    if not isinstance(result, dict):
        return {"result": result}
    return result


def run_ask(conn, payload, owner, ctx, job_id=None):
    _ = owner
    payload = dict(payload or {})
    progress, cancelled = (None, None)
    if job_id:
        progress, cancelled = _control(conn, job_id)
        progress(10, "start")
        _raise_if_cancelled(cancelled)
    prov = _providers(ctx, conn)
    live = prov.llm if getattr(prov, "mode", "mock") == "live" else None
    scope = benchmarks.Scope.from_payload(payload).resolve(conn)
    result = qa.answer(conn, payload.get("question", ""), llm=live,
                       scope=scope, owner=owner or "")
    if progress is not None:
        progress(90, "answered")
    if not isinstance(result, dict):
        return {"answer": result}
    return result


def run_analyst(conn, payload, owner, ctx, job_id=None):
    """One persistent Foap Analyst turn, off the event loop.

    Deterministic: numbers come from the shared calculation engine,
    never the LLM. Progress checkpoints bracket routing, analysis
    and persistence so cancellation lands between stages.
    """
    _ = ctx
    payload = dict(payload or {})
    progress, cancelled = (None, None)
    if job_id:
        progress, cancelled = _control(conn, job_id)
        progress(5, "start")
        _raise_if_cancelled(cancelled)
    out = analyst_chat.answer_turn(
        conn, owner or "", payload.get("question", ""),
        conversation_id=payload.get("conversation_id"),
        # None passes through: omitted scope inherits the
        # conversation's scope, explicit {} clears it (A20).
        scope=payload.get("scope"),
        objective=payload.get("objective", "reach"),
        language=payload.get("language"),
        rank_by=payload.get("rank_by"),
        max_points=payload.get("max_points"))
    if progress is not None:
        progress(90, "answered")
    if not isinstance(out, dict):
        return {"result": out}
    return out


def run_video_analysis(conn, payload, owner, ctx, job_id=None):
    """Guided-upload analysis off the event loop.

    The payload snapshot (bound at Analyse-press time) is re-checked
    inside: changed inputs abort honestly, and a late result never
    overwrites a newer analysis. Draft status mirrors the lifecycle
    (queued at submit, analyzing at start, ready_for_review / failed
    / cancelled on the way out); cancellation flows through the
    standard job path.
    """
    from creative_intel import drafts as drafts_mod
    from creative_intel import video_analysis
    payload = dict(payload or {})
    # Resolve the snapshot first so even a cancel-before-start lands
    # the draft in cancelled instead of stranding it in queued.
    snapshot = payload.get("snapshot") or {}
    if not snapshot:
        raise ValueError("video_analysis needs a bound snapshot")
    did = snapshot.get("draft_id") or ""
    progress, cancelled = (None, None)
    attempt_token = ""
    if job_id:
        progress, cancelled = _control(conn, job_id)
        try:
            attempt_token = \
                (jobs_mod.get(conn, job_id) or {}).get("run_token") or ""
        except Exception:
            attempt_token = ""
        progress(5, "start")
        try:
            _raise_if_cancelled(cancelled)
        except jobs_mod.JobCancelled:
            if did:
                try:
                    drafts_mod.update_draft(conn, did, status="cancelled")
                except Exception:
                    pass
            raise
    queued_at = ""
    if job_id:
        try:
            row = jobs_mod.get(conn, job_id) or {}
            queued_at = row.get("created_at") or ""
        except Exception:
            queued_at = ""
    media_dir = (ctx or {}).get("media_dir")
    try:
        # The endpoint submits as queued; the worker owns the
        # queued -> analyzing transition when work actually starts.
        if did:
            try:
                drafts_mod.update_draft(conn, did, status="analyzing")
            except Exception:
                pass
        return video_analysis.run(
            conn, snapshot, owner=owner or "", media_dir=media_dir or "",
            progress=progress, cancelled=cancelled, queued_at=queued_at,
            job_id=job_id, run_token=attempt_token)
    except jobs_mod.JobCancelled:
        # Owner cancel: the draft returns to cancelled (re-analysable),
        # never strands in analyzing.
        if did:
            try:
                drafts_mod.update_draft(conn, did, status="cancelled")
            except Exception:
                pass
        raise
    except jobs_mod.StaleAttempt:
        # Superseded attempt: the replacement owns the job and the
        # draft now. Touch neither — especially not failed, which
        # would clobber the replacement's analyzing state.
        raise
    except Exception:
        # ProviderUnavailable, timeouts, corrupt media, stale inputs:
        # every failure path lands the draft in failed with the job
        # error preserved on the job row. Never strand in analyzing.
        if did:
            try:
                drafts_mod.update_draft(conn, did, status="failed")
            except Exception:
                pass
        raise


HANDLERS = {
    "pipeline": run_pipeline,
    "ask": run_ask,
    "analyst": run_analyst,
    "video_analysis": run_video_analysis,
}


def run(conn, kind, payload, owner, ctx, job_id):
    try:
        handler = HANDLERS[kind]
    except KeyError:
        raise ValueError("unknown job kind %r" % (kind,))
    return handler(conn, payload, owner, ctx or {}, job_id)

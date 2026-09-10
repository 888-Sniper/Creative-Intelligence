"""Product routes (FastAPI port of the legacy data-surface).

Each branch calls the same ``creative_intel`` library functions with
the same arguments as the stdlib server; only the HTTP shell changed.
Shared blocks (creatives list, compare) are imported from ``server``
so both shells run identical logic during the transition.
"""

from __future__ import annotations

import asyncio
import functools
import mimetypes
import os
import sqlite3
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from creative_intel import (  # noqa: E402
    benchmarks,
    cohorts,
    export_gate,
    media,
    qa,
    replay,
    retention,
    schema,
    sync,
)
from creative_intel import (
    providers as providers_mod,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from ci_backend import actions as legacy  # noqa: E402
from ci_backend import employees as emp  # noqa: E402
from ci_backend.deps import (  # noqa: E402
    get_current_employee,
    get_product_conn,
    get_providers,
    json_payload,
    query_multidict,
)

router = APIRouter(tags=["product"])


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": str(exc)})


def _guarded():
    return Depends(get_current_employee)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("/api/health")
def health(request: Request, prov=Depends(get_providers)):
    return {"ok": True, "provider_mode": prov.mode,
            "keys": providers_mod.key_status(),
            "providers": providers_mod.provider_matrix()}


@router.get("/api/campaigns")
def campaigns(request: Request, conn=Depends(get_product_conn),
              _emp=Depends(get_current_employee)):
    try:
        return benchmarks.benchmark(
            conn, "campaign",
            benchmarks.Scope.from_query(query_multidict(request)).normalized())
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/campaigns/recommendations")
def recommendations(request: Request, conn=Depends(get_product_conn),
                    _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    name = (q.get("name", [""])[0] if q.get("name") else "")
    if not name:
        raise _conflict(ValueError("recommendations need a campaign name"))
    rank_by = ((q.get("rank_by", ["cpa"])[0]
                if q.get("rank_by") else "cpa") or "cpa").lower()
    try:
        return benchmarks.campaign_recommendations(
            conn, name, benchmarks.Scope.from_query(q), rank_by)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/benchmarks")
def benchmark_route(request: Request, conn=Depends(get_product_conn),
                    _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    try:
        return benchmarks.benchmark(
            conn, (q.get("group_by", ["hook_type"])[0]
                   if q.get("group_by") else "hook_type"),
            benchmarks.Scope.from_query(q).normalized())
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/creatives")
def creatives(request: Request, conn=Depends(get_product_conn),
              _emp=Depends(get_current_employee)):
    try:
        return legacy.build_creatives_list(conn, query_multidict(request))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/retention")
def retention_segments(request: Request, conn=Depends(get_product_conn),
                       _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    try:
        return retention.join_segments(
            conn, q.get("creative_key", [""])[0]
            if q.get("creative_key") else "")
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/compare")
def compare(request: Request, conn=Depends(get_product_conn),
            _emp=Depends(get_current_employee)):
    try:
        return legacy.build_compare(conn, query_multidict(request))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/retention/patterns")
def retention_patterns(request: Request, conn=Depends(get_product_conn),
                       _emp=Depends(get_current_employee)):
    try:
        return retention.patterns(
            conn, benchmarks.Scope.from_query(query_multidict(request)))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/retention/curve")
def retention_curve(request: Request, conn=Depends(get_product_conn),
                    _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    try:
        return retention.curve(
            conn, q.get("creative_key", [""])[0]
            if q.get("creative_key") else "")
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/compare/periods")
def compare_periods(request: Request, conn=Depends(get_product_conn),
                    _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    try:
        scope = benchmarks.Scope.from_query(
            q, ignore=("a_from", "a_to", "b_from", "b_to",
                       "label_a", "label_b"))
        return benchmarks.compare_periods(
            conn, (q.get("a_from", [""])[0] if q.get("a_from") else ""),
            (q.get("a_to", [""])[0] if q.get("a_to") else ""),
            (q.get("b_from", [""])[0] if q.get("b_from") else ""),
            (q.get("b_to", [""])[0] if q.get("b_to") else ""),
            filters=scope,
            label_a=(q.get("label_a", ["Period A"])[0]
                     if q.get("label_a") else "Period A") or "Period A",
            label_b=(q.get("label_b", ["Period B"])[0]
                     if q.get("label_b") else "Period B") or "Period B")
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/replay")
def replay_history(request: Request, conn=Depends(get_product_conn),
                   _emp=Depends(get_current_employee)):
    return replay.history(conn)


@router.get("/api/sync/status")
def sync_status(request: Request, conn=Depends(get_product_conn),
                _emp=Depends(get_current_employee)):
    return sync.status(conn)


class SyncJobCreate(BaseModel):
    source: str = Field(pattern="^(meta|tiktok|sheets|drive)$")
    name: str = Field(min_length=1, max_length=120)
    params: dict = Field(default_factory=dict)
    enabled: bool = True


class SyncJobUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    params: dict | None = None
    enabled: bool | None = None


def _job_or_404(conn, job_id: str) -> dict:
    job = sync.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Unknown sync job."})
    return job


@router.get("/api/sync/jobs")
def sync_jobs_list(request: Request, conn=Depends(get_product_conn),
                   _emp=Depends(get_current_employee)):
    return {"jobs": sync._jobs_with_runs(conn)}


@router.post("/api/sync/jobs")
async def sync_job_create(request: Request, conn=Depends(get_product_conn),
                          who=Depends(get_current_employee)):
    try:
        body = SyncJobCreate.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid sync job: %s" % exc})
    try:
        job = sync.create_job(conn, body.source, body.name, body.params,
                              owner=who.id)
    except ValueError as exc:
        raise _conflict(exc)
    if not body.enabled:
        job = sync.set_job_enabled(conn, job["id"], False)
    return {"job": job}


@router.patch("/api/sync/jobs/{job_id}")
async def sync_job_update(job_id: str, request: Request,
                          conn=Depends(get_product_conn),
                          _emp=Depends(get_current_employee)):
    from urllib.parse import unquote
    _job_or_404(conn, unquote(job_id))
    try:
        body = SyncJobUpdate.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid sync job: %s" % exc})
    try:
        if body.name is not None or body.params is not None:
            sync.update_job(conn, unquote(job_id), name=body.name,
                            params=body.params)
        if body.enabled is not None:
            sync.set_job_enabled(conn, unquote(job_id), body.enabled)
    except ValueError as exc:
        raise _conflict(exc)
    return {"job": sync.get_job(conn, unquote(job_id))}


@router.delete("/api/sync/jobs/{job_id}")
def sync_job_delete(job_id: str, request: Request,
                    conn=Depends(get_product_conn),
                    _emp=Depends(get_current_employee)):
    from urllib.parse import unquote
    _job_or_404(conn, unquote(job_id))
    sync.delete_job(conn, unquote(job_id))
    return {"ok": True}


@router.post("/api/sync/jobs/{job_id}/run")
def sync_job_run(job_id: str, request: Request,
                 conn=Depends(get_product_conn),
                 who=Depends(get_current_employee)):
    from urllib.parse import unquote
    job = _job_or_404(conn, unquote(job_id))
    bearer = None
    if job["source"] in ("sheets", "drive") \
            and (job["params"] or {}).get("google_auth"):
        from ci_backend import google_oauth as goog
        try:
            with request.app.state.ci_sessions() as session:
                headers = goog.bearer_headers(
                    session, who.id, request.app.state.ci_settings)
        except (emp.StoreError, goog.GoogleError) as exc:
            raise _conflict(exc)
        bearer = headers["Authorization"].split(" ", 1)[1]
    if bearer:
        def _fetch():
            return sync.fetch_job(job["source"], job["params"],
                                  bearer=bearer)
    else:
        def _fetch():
            return sync.fetch_job(job["source"], job["params"])
    try:
        out = sync.import_once(
            conn, job["source"], _fetch, job_id=job["id"])
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)
    out["job"] = sync.get_job(conn, job["id"])
    return out


@router.get("/api/views")
def views(request: Request, conn=Depends(get_product_conn),
          _emp=Depends(get_current_employee)):
    return legacy.list_views(conn)


@router.get("/api/reviews")
def reviews(request: Request, conn=Depends(get_product_conn),
            _emp=Depends(get_current_employee)):
    return qa.list_reviews(conn)


@router.get("/api/compare/campaigns")
def compare_campaigns(request: Request, conn=Depends(get_product_conn),
                      _emp=Depends(get_current_employee)):
    try:
        return legacy.expert2_compare_route(conn, query_multidict(request))
    except ValueError as exc:
        raise _conflict(exc)


@router.get("/api/cohorts")
def list_cohorts(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    try:
        return cohorts.list_cohorts(conn)
    except ValueError as exc:
        raise _conflict(exc)


@router.get("/api/cohorts/build")
def cohort_build(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    try:
        return legacy.expert2_cohort_build_route(conn,
                                                 query_multidict(request))
    except ValueError as exc:
        raise _conflict(exc)


# ---------------------------------------------------------------------------
# Writes / actions
# ---------------------------------------------------------------------------


_ACTION_ROUTES = {
    "/api/ingest": "ingest",
    "/api/media/upload": "media-upload",
    "/api/connect/drive": "connect-drive",
    "/api/connect/sheets": "connect-sheets",
    "/api/connect/meta": "connect-meta",
    "/api/connect/tiktok": "connect-tiktok",
    "/api/sync/run": "sync-now",
    "/api/pipeline/run": "pipeline",
    "/api/retention": "retention",
    "/api/views": "save-view",
    "/api/views/delete": "delete-view",
}


@router.post("/api/ask")
async def ask(request: Request, conn=Depends(get_product_conn),
              prov=Depends(get_providers),
              _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    live = (prov.llm if getattr(prov, "mode", "mock") == "live" else None)
    try:
        return qa.answer(conn, body.get("question", ""), llm=live,
                         scope=benchmarks.Scope.from_payload(body))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.post("/api/reviews/mark")
async def reviews_mark(request: Request, conn=Depends(get_product_conn),
                       _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    try:
        pending = qa.mark_reviewed(conn, int(body["review_id"]))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)
    return {"ok": True, "pending": pending}


@router.post("/api/export")
async def export(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    try:
        export_gate.check_reviews(conn)
        result = export_gate.build_one_pager(
            conn, body.get("creative_keys", []),
            benchmarks.benchmark(conn, "hook_type"),
            override=bool(body.get("override")))
    except export_gate.ExportBlocked as exc:
        raise HTTPException(status_code=409, detail={
            "error": str(exc), "missing": exc.missing})
    except (ValueError, emp.StoreError) as exc:
        raise _conflict(exc)
    replay.log(conn, "export", {"creative_keys": body.get("creative_keys", []),
                                "override": bool(body.get("override"))})
    return result


@router.post("/api/replay/run")
def replay_run(request: Request, conn=Depends(get_product_conn),
               prov=Depends(get_providers),
               _emp=Depends(get_current_employee)):
    hist = replay.history(conn)
    mem = sqlite3.connect(":memory:")
    schema.init_db(mem)
    n = 0
    for entry in hist:
        if entry["action"] in ("export", "report-override"):
            continue
        legacy.apply_action(mem, entry["action"], entry["payload"], prov)
        n += 1
    live = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    replayed = mem.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    mem.close()
    return {"replayed": n, "live_ads": live, "replayed_ads": replayed,
            "matches_live": live == replayed}


@router.post("/api/cohorts")
async def save_cohort(request: Request, conn=Depends(get_product_conn),
                      _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    try:
        return cohorts.save_cohort(conn, body.get("name", ""),
                                   body.get("filters", {}))
    except ValueError as exc:
        raise _conflict(exc)


@router.post("/api/compare/campaigns")
async def compare_campaigns_post(request: Request,
                                 conn=Depends(get_product_conn),
                                 _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    try:
        pseudo = {"campaigns": [",".join(body.get("campaigns", []) or [])],
                  "rank_by": [body.get("rank_by", "cpa")]}
        for key, vals in ((body.get("filters") or {}).items()):
            pseudo[key] = (list(vals) if isinstance(vals, list) else [vals])
        return legacy.expert2_compare_route(conn, pseudo)
    except ValueError as exc:
        raise _conflict(exc)


@router.post("/api/report")
async def report(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    body = await json_payload(request)
    try:
        return legacy.expert2_report_route(conn, body)
    except ValueError as exc:
        raise _conflict(exc)


@router.post("/api/creatives/{key}/verify")
async def creative_verify(key: str, request: Request,
                          conn=Depends(get_product_conn),
                          prov=Depends(get_providers),
                          who=Depends(get_current_employee)):
    return await _run_action(conn, prov, "verify", {"creative_key": unquote(key)},
                             actor=who.id)


@router.post("/api/creatives/{key}/annotate")
async def creative_annotate(key: str, request: Request,
                            conn=Depends(get_product_conn),
                            prov=Depends(get_providers),
                            who=Depends(get_current_employee)):
    body = await json_payload(request)
    return await _run_action(conn, prov, "annotate",
                             {"creative_key": unquote(key),
                              "annotation": body.get("annotation", {})},
                             actor=who.id)


@router.post("/api/{action:path}")
async def action_dispatch(action: str, request: Request,
                          conn=Depends(get_product_conn),
                          prov=Depends(get_providers),
                          who=Depends(get_current_employee)):
    path = "/api/" + action
    if path not in _ACTION_ROUTES:
        raise HTTPException(status_code=404, detail={"error": "not found"})
    if path == "/api/media/upload" and request.headers.get(
            "content-type", "").split(";")[0].strip() == "multipart/form-data":
        return await _media_upload_multipart(request, conn)
    body = await json_payload(request)
    return await _run_action(conn, prov, _ACTION_ROUTES[path], body,
                             actor=who.id, request=request)


async def _media_upload_multipart(request: Request, conn):
    """Multipart creative upload: bytes ride outside JSON.

    The file streams in chunks so the real media.MAX_BYTES (100 MB)
    limit is enforced by counting, not by the JSON body cap.
    """
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=409,
                            detail={"error": "upload needs multipart form"})
    creative_key = form.get("creative_key") or ""
    upload = form.get("file")
    read = getattr(upload, "read", None)
    filename = getattr(upload, "filename", "") or ""
    if not creative_key or read is None or not filename:
        raise HTTPException(
            status_code=409,
            detail={"error": "upload needs creative_key and a file part"})
    chunks, total = [], 0
    while True:
        piece = await read(media.CHUNK_BYTES)
        if not piece:
            break
        total += len(piece)
        if total > media.MAX_BYTES:
            raise HTTPException(
                status_code=409,
                detail={"error": "upload exceeds %d MB"
                        % (media.MAX_BYTES // (1024 * 1024))})
        chunks.append(piece)
    content = b"".join(chunks)
    try:
        return media.save_media_bytes(
            conn, legacy._media_dir(), creative_key, filename, content,
            getattr(upload, "content_type", None) or None)
    except ValueError as exc:
        raise _conflict(exc)


def _resolve_google_bearer(payload: dict, actor: str,
                           request) -> None:
    """Attach a short-lived Google access token for private-file imports.

    Only when the caller explicitly opts in with google_auth. The token
    lives in server memory for this call and is stripped before the
    replay log, so it never lands in the database or logs.
    """
    if not isinstance(payload, dict) or not payload.get("google_auth"):
        return
    from ci_backend import google_oauth as goog
    try:
        with request.app.state.ci_sessions() as session:
            headers = goog.bearer_headers(
                session, actor, request.app.state.ci_settings)
    except (emp.StoreError, goog.GoogleError) as exc:
        raise _conflict(exc)
    payload["_google_bearer"] = headers["Authorization"].split(" ", 1)[1]


async def _run_action(conn, prov, action: str, payload: dict, actor: str = "",
                      request=None):
    """Run one product action without blocking the event loop.

    Video/AI work (pipeline, imports, media) is synchronous blocking
    code by design, so it hops to a worker thread; the loop stays free
    for health, auth, and other requests. The product SQLite handle
    is single-owner per request (check_same_thread=False) and the
    replay log stays on the loop thread after the hop.
    """
    if action in ("connect-sheets", "connect-drive") and request is not None:
        _resolve_google_bearer(payload, actor, request)
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            None, functools.partial(legacy.apply_action, conn, action,
                                    payload, prov, actor=actor))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)
    finally:
        if isinstance(payload, dict):
            payload.pop("_google_bearer", None)
    if action != "media-upload":
        replay.log(conn, action, payload)
    return result


# ---------------------------------------------------------------------------
# Media bytes, assets, shell
# ---------------------------------------------------------------------------


@router.get("/media/by-creative/{key}")
def media_by_creative(key: str, request: Request,
                      conn=Depends(get_product_conn),
                      _emp=Depends(get_current_employee)):
    from urllib.parse import unquote
    try:
        items = media.list_for_creative(conn, unquote(key))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return {"media": items}


@router.get("/media/{media_id}")
def serve_media(media_id: str, request: Request,
                conn=Depends(get_product_conn),
                _emp=Depends(get_current_employee)):
    # Authenticated employees only, private cache: media rows are
    # account data, never shared-cacheable. FileResponse serves byte
    # ranges so video/audio seek instead of downloading whole files.
    try:
        info = media.describe(conn, legacy._media_dir(), media_id)
        path = media.file_path(conn, legacy._media_dir(), media_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return FileResponse(path, media_type=info["mime"],
                        filename=info["filename"],
                        headers={"Cache-Control": "private, max-age=86400"})


_ALLOWED_ASSET_EXTS = (".png", ".svg", ".ico", ".webp")
# Hashed Vite build assets: safe to cache immutably, served from the
# React dist directory only (never from the legacy tree).
_ALLOWED_DIST_EXTS = (".js", ".css", ".woff2")


def _index_response():
    entry = legacy.react_index()
    headers = None
    if os.path.normpath(entry) != os.path.normpath(legacy.WEB_INDEX):
        # React build ships zero inline scripts, so a strict policy is
        # safe here. The legacy fallback still uses inline scripts and
        # keeps relying on the other headers (see _security_headers).
        headers = {"Content-Security-Policy": "default-src 'self'; "
                   "img-src 'self' data: https:; "
                   "style-src 'self' 'unsafe-inline'"}
    return FileResponse(entry, media_type="text/html; charset=utf-8",
                        headers=headers)


@router.get("/assets/{name}")
def serve_asset(name: str):
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail={"error": "not found"})
    ext = os.path.splitext(name)[1].lower()
    if ext in _ALLOWED_DIST_EXTS:
        path = os.path.join(legacy.REACT_ASSETS_DIR, name)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404,
                                detail={"error": "not found"})
        ctype, _ = mimetypes.guess_type(path)
        return FileResponse(
            path, media_type=ctype or "application/octet-stream",
            headers={"Cache-Control": "public, max-age=31536000, immutable"})
    if ext not in _ALLOWED_ASSET_EXTS:
        raise HTTPException(status_code=404, detail={"error": "not found"})
    path = os.path.join(legacy.ASSETS_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail={"error": "not found"})
    ctype, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=ctype or "application/octet-stream",
                        headers={"Cache-Control": "public, max-age=86400"})


# Brand files referenced by the React shell (single source in Web/assets;
# no duplication into the frontend tree).
_BRAND_FILES = {"foap-logo.png": "image/png",
                "favicon.png": "image/png"}


@router.get("/foap-logo.png")
def serve_logo():
    return _brand_file("foap-logo.png")


@router.get("/favicon.png")
def serve_favicon():
    return _brand_file("favicon.png")


def _brand_file(name: str):
    path = os.path.join(legacy.ASSETS_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail={"error": "not found"})
    return FileResponse(path, media_type=_BRAND_FILES[name],
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/")
def index():
    return _index_response()


@router.get("/index.html")
def index_alias():
    return _index_response()


# React Router client paths: serve the app shell so deep links and
# refreshes work (item 51). Explicit list — unknown paths still 404.
_SPA_PATHS = ("campaigns", "creatives", "compare", "benchmarks",
              "reports", "profile", "settings", "admin")


@router.get("/{spa_path}")
def spa_fallback(spa_path: str):
    if spa_path not in _SPA_PATHS:
        raise HTTPException(status_code=404, detail={"error": "not found"})
    return _index_response()

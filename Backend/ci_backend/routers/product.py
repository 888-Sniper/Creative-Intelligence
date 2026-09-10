"""Product routes (FastAPI port of the legacy data-surface).

Each branch calls the same ``creative_intel`` library functions with
the same arguments as the stdlib server; only the HTTP shell changed.
Shared blocks (creatives list, compare) are imported from ``server``
so both shells run identical logic during the transition.
"""

from __future__ import annotations

import mimetypes
import os
import sqlite3
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402

from ci_backend import actions as legacy  # noqa: E402
from ci_backend import employees as emp  # noqa: E402
from ci_backend.deps import (  # noqa: E402
    get_current_employee,
    get_product_conn,
    get_providers,
    json_payload,
    query_multidict,
)
from creative_intel import (  # noqa: E402
    benchmarks,
    cohorts,
    export_gate,
    media,
    providers as providers_mod,
    qa,
    replay,
    retention,
    schema,
    sync,
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
    return _run_action(conn, prov, "verify", {"creative_key": unquote(key)},
                       actor=who.id)


@router.post("/api/creatives/{key}/annotate")
async def creative_annotate(key: str, request: Request,
                            conn=Depends(get_product_conn),
                            prov=Depends(get_providers),
                            who=Depends(get_current_employee)):
    body = await json_payload(request)
    return _run_action(conn, prov, "annotate",
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
    body = await json_payload(request)
    return _run_action(conn, prov, _ACTION_ROUTES[path], body,
                       actor=who.id)


def _run_action(conn, prov, action: str, payload: dict, actor: str = ""):
    try:
        result = legacy.apply_action(conn, action, payload, prov,
                                     actor=actor)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)
    if action != "media-upload":
        replay.log(conn, action, payload)
    return result


# ---------------------------------------------------------------------------
# Media bytes, assets, shell
# ---------------------------------------------------------------------------


@router.get("/media/{media_id}")
def serve_media(media_id: str, request: Request,
                conn=Depends(get_product_conn),
                _emp=Depends(get_current_employee)):
    try:
        blob, mime, _filename = media.load_bytes(
            conn, legacy._media_dir(), media_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return Response(content=blob, media_type=mime,
                    headers={"Cache-Control": "public, max-age=86400"})


_ALLOWED_ASSET_EXTS = (".png", ".svg", ".ico", ".webp")


@router.get("/assets/{name}")
def serve_asset(name: str):
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail={"error": "not found"})
    if os.path.splitext(name)[1].lower() not in _ALLOWED_ASSET_EXTS:
        raise HTTPException(status_code=404, detail={"error": "not found"})
    path = os.path.join(legacy.ASSETS_DIR, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail={"error": "not found"})
    ctype, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=ctype or "application/octet-stream",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/")
def index():
    return FileResponse(legacy.WEB_INDEX,
                        media_type="text/html; charset=utf-8")


@router.get("/index.html")
def index_alias():
    return FileResponse(legacy.WEB_INDEX,
                        media_type="text/html; charset=utf-8")

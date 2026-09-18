"""Product routes (FastAPI port of the legacy data-surface).

Each branch calls the same ``creative_intel`` library functions with
the same arguments as the stdlib server; only the HTTP shell changed.
Shared blocks (creatives list, compare) are imported from ``server``
so both shells run identical logic during the transition.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import functools
import hashlib
import inspect
import mimetypes
import re
import os
import sqlite3
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", ".."))

from creative_intel import (  # noqa: E402
    analyst,
    analyst_chat,
    analyst_workbook,
    benchmarks,
    cohorts,
    export_gate,
    media,
    ooxml,
    period_compare,
    qa,
    replay,
    retention,
    schema,
    sync,
    thumbnails,
)
from creative_intel import (  # noqa: E402
    jobs as jobs_mod,
)
from creative_intel import (
    provider_inventory as inventory_mod,
)
from creative_intel import (
    providers as providers_mod,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response  # noqa: E402
from pydantic import BaseModel, Field, field_validator, model_validator  # noqa: E402

from ci_backend import actions as legacy  # noqa: E402
from ci_backend import employees as emp  # noqa: E402
from ci_backend import product_audit as paudit  # noqa: E402
from ci_backend.deps import (  # noqa: E402
    SYNC_RATE_LIMIT,
    UPLOAD_RATE_LIMIT,
    ai_rate_limit,
    check_user_limit,
    get_current_admin,
    get_current_employee,
    get_product_conn,
    get_providers,
    json_payload,
    query_multidict,
)


def _provider_failure(exc: Exception) -> HTTPException:
    """Map a provider failure to HTTP without leaking internals.

    Paused AI (honest not-configured message) -> 409 like other
    state conflicts; a chosen-model transport failure (marked
    [provider=<id>] by the managed dispatcher) -> 502 Bad Gateway.
    """
    text = str(exc)
    # Substring match: job rows carry str(exc)[:500], so a wrapped
    # message still classifies correctly.
    if inventory_mod.NOT_CONFIGURED_MESSAGE in text:
        return HTTPException(
            status_code=409,
            detail={"error": inventory_mod.NOT_CONFIGURED_MESSAGE})
    return HTTPException(status_code=502, detail={"error": text})


router = APIRouter(tags=["product"])

# Bounded worker pool for blocking video/AI work (item 24): the event
# loop never runs pipeline/media/import code directly, and at most
# four such jobs run concurrently per process.
_WORKERS = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="ci-worker")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": str(exc)})


def _guarded():
    return Depends(get_current_employee)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


@router.get("/api/health")
def health(request: Request, prov=Depends(get_providers)):
    """Minimal public health: liveness + mode only. Key inventory and
    the provider matrix stay behind authenticated /api/providers/status."""
    return {"ok": True, "provider_mode": prov.mode}


@router.get("/api/providers/status")
def providers_status(request: Request,
                     _emp=Depends(get_current_employee)):
    """Safe AI readiness for the demo (item 30): per-capability
    configured/missing plus adapter names. Never carries key values,
    bearer tokens, or provider secrets."""
    caps = {}
    for cap, roster in (
            ("stt", providers_mod.LiveBundle.STT_ROSTER),
            ("vision", providers_mod.LiveBundle.VISION_ROSTER),
            ("llm", providers_mod.LiveBundle.LLM_ROSTER)):
        names = sorted({p for p, _model, _tier in roster
                        if providers_mod._configured(p)})
        caps[cap] = {"status": "configured" if names else "missing",
                     "adapters": names}
    return {"mode": providers_mod.mode(), "capabilities": caps}


@router.get("/api/campaigns")
def campaigns(request: Request, conn=Depends(get_product_conn),
              _emp=Depends(get_current_employee)):
    try:
        return benchmarks.benchmark(
            conn, "campaign",
            benchmarks.Scope.from_query(query_multidict(request)).resolve(conn).normalized())
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/campaigns/meta")
def campaigns_meta(request: Request, conn=Depends(get_product_conn),
                   _emp=Depends(get_current_employee)):
    """Per-campaign display metadata (client, platforms, derived status).

    Additive read-only surface for the Campaigns screen filters and
    table; the aggregated /api/campaigns payload is unchanged.
    """
    try:
        return benchmarks.campaign_meta(conn)
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
            conn, name, benchmarks.Scope.from_query(q).resolve(conn), rank_by)
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
            benchmarks.Scope.from_query(q).resolve(conn).normalized())
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
            conn, benchmarks.Scope.from_query(query_multidict(request)).resolve(conn))
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


@router.get("/api/kpis/compare")
def kpis_compare(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    q = query_multidict(request)
    try:
        scope = benchmarks.Scope.from_query(q)
        return period_compare.compare_kpis(conn, scope.resolve(conn).normalized())
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


@router.get("/api/kpis/daily")
def kpis_daily(request: Request, conn=Depends(get_product_conn),
               _emp=Depends(get_current_employee)):
    """Per-day totals for trend charts (same scope semantics as /api/campaigns)."""
    q = query_multidict(request)
    try:
        scope = benchmarks.Scope.from_query(q)
        days = (q.get("days", [""])[0] if q.get("days") else "") or 30
        return benchmarks.daily_series(conn, scope.resolve(conn).normalized(), days)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        raise _conflict(exc)


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


# ---------------------------------------------------------------------------
# Explicit request schemas for every external write API.
#
# json_payload() stays the tolerant transport (size-capped, {} on empty),
# but each handler validates shape here first: enum membership, maximum
# lengths, list limits, ISO dates and allowed filter/KPI values. Invalid
# bodies fail with the same 409 contract as downstream ValueErrors, so
# malformed input never reaches library code as a 500. Unknown extra
# keys are ignored (Pydantic default), keeping the UI forward-compatible.
# ---------------------------------------------------------------------------

# Filter axes callers may send (Scope axes plus cohort project lists).
_FILTER_KEYS = (set(benchmarks.Scope.AXES)
                | {"include_projects", "exclude_projects"})
# KPI values build_report() understands (rankable metrics + volume).
_REPORT_KPIS = (set(benchmarks.KPI_KEYS)
                | {"spend", "impressions", "clicks", "conversions",
                   "cpc"})


def _iso_day(value, *, what: str) -> str:
    import datetime
    import re
    text = str(value or "").strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        raise ValueError("%s must be YYYY-MM-DD, got %r" % (what, value))
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        raise ValueError("%s is not a real date: %r" % (what, value))
    return text


def _filter_dict(values, *, what: str) -> dict:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("%s.filters must be an object" % what)
    if len(values) > 20:
        raise ValueError("%s.filters has too many axes" % what)
    for key, vals in values.items():
        if key not in _FILTER_KEYS:
            raise ValueError("%s.filters has unknown key %r" % (what, key))
        items = [vals] if isinstance(vals, str) else vals
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError(
                "%s.filters[%r] must be a list of at most 50" % (what, key))
        for item in items:
            if not isinstance(item, str) or not item or len(item) > 200:
                raise ValueError(
                    "%s.filters[%r] values must be 1-200 chars"
                    % (what, key))
    for key in ("date_from", "date_to"):
        vals = values.get(key)
        items = [vals] if isinstance(vals, str) else (vals or [])
        if items and items[0] not in ("", "all"):
            _iso_day(items[0], what="%s.filters[%s]" % (what, key))
    return values


def _kpi(value, *, what: str) -> str:
    text = str(value or "").lower()
    if text not in benchmarks.KPI_KEYS:
        raise ValueError("%s must be one of %s"
                         % (what, sorted(benchmarks.KPI_KEYS)))
    return text


def _validated(model, raw, label: str):
    try:
        return model.model_validate(raw)
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid %s: %s" % (label, exc)})


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    filters: dict = Field(default_factory=dict)

    @field_validator("filters", mode="before")
    @classmethod
    def _check_filters(cls, values):
        return _filter_dict(values, what="ask")


class ReviewsMarkBody(BaseModel):
    review_id: int = Field(gt=0, le=2 ** 31)


class ExportBody(BaseModel):
    creative_keys: list[str] = Field(min_length=1, max_length=50)
    override: bool = False

    @field_validator("creative_keys", mode="before")
    @classmethod
    def _check_keys(cls, values):
        return _str_list(values, what="export", allow_empty=False)


def _str_list(values, *, what: str, max_items=50, max_len=200,
              allow_empty=True) -> list:
    items = [values] if isinstance(values, str) else values
    if not isinstance(items, list):
        raise ValueError("%s must be a list of strings" % what)
    if len(items) > max_items:
        raise ValueError("%s has more than %d items" % (what, max_items))
    if not allow_empty and not items:
        raise ValueError("%s must not be empty" % what)
    for item in items:
        if not isinstance(item, str) or not item or len(item) > max_len:
            raise ValueError("%s items must be 1-%d chars" % (what, max_len))
    return items


class CohortBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: dict = Field(default_factory=dict)

    @field_validator("filters", mode="before")
    @classmethod
    def _check_filters(cls, values):
        return _filter_dict(values, what="cohort")


class CompareBody(BaseModel):
    campaigns: list[str] = Field(default_factory=list, max_length=50)
    rank_by: str = "cpa"
    filters: dict = Field(default_factory=dict)

    @field_validator("filters", mode="before")
    @classmethod
    def _check_filters(cls, values):
        return _filter_dict(values, what="compare")

    @field_validator("rank_by", mode="before")
    @classmethod
    def _check_rank(cls, value):
        return _kpi(value or "cpa", what="rank_by")


class ReportBody(BaseModel):
    campaigns: list[str] | None = Field(default=None, max_length=50)
    kpis: list[str] = Field(default_factory=lambda: ["cpa", "ctr"],
                            max_length=12)
    benchmark: str | None = Field(default=None, max_length=120)
    benchmark_scope: str = Field(default="filters",
                                 pattern="^(filters|global)$")
    rank_by: str | None = None
    override: bool = False
    strict_human: bool = False
    filters: dict = Field(default_factory=dict)
    format: str = Field(default="one-pager",
                        pattern="^(one-pager|csv|deck|pptx|xlsx)$")

    @field_validator("filters", mode="before")
    @classmethod
    def _check_filters(cls, values):
        return _filter_dict(values, what="report")

    @field_validator("rank_by", mode="before")
    @classmethod
    def _check_rank(cls, value):
        return None if value is None else _kpi(value, what="rank_by")

    @field_validator("kpis", mode="before")
    @classmethod
    def _kpis(cls, values):
        items = _str_list(values if values is not None else [], what="kpis",
                          max_items=12, max_len=40)
        unknown = [k for k in items if k.lower() not in _REPORT_KPIS]
        if unknown:
            raise ValueError("unknown kpis: %s" % unknown)
        if not items:
            raise ValueError("kpis must not be empty")
        return [k.lower() for k in items]


class AnnotateBody(BaseModel):
    annotation: dict = Field()

    @field_validator("annotation", mode="before")
    @classmethod
    def _check_annotation(cls, values):
        return _bounded_dict(values, what="annotation")


def _bounded_dict(values, *, what: str, max_keys=100) -> dict:
    if not isinstance(values, dict):
        raise ValueError("%s must be an object" % what)
    if len(values) > max_keys:
        raise ValueError("%s has more than %d keys" % (what, max_keys))
    return values


# Per-route schemas for the generic action-dispatch surface. Routes not
# listed here take a free-form object and rely on per-action library
# validation (ValueError -> 409) behind the dispatch allowlist.


class IngestBody(BaseModel):
    platform: str = Field(min_length=1, max_length=120)
    source: str = Field(default="upload", max_length=120)
    csv: str | None = None
    xlsx_b64: str | None = None

    @model_validator(mode="after")
    def _need_payload_body(self):
        if not self.csv and not self.xlsx_b64:
            raise ValueError(
                "ingest needs csv text or xlsx_b64 plus platform")
        return self


class MediaUploadJSONBody(BaseModel):
    creative_key: str = Field(min_length=1, max_length=200)
    filename: str = Field(default="", max_length=255)
    content_b64: str = Field(min_length=1)
    mime: str | None = Field(default=None, max_length=127)


class VideoValidateBody(BaseModel):
    media_id: int = Field(gt=0, le=2 ** 31)
    draft_id: str | None = Field(default=None, max_length=64)


class DraftCreateBody(BaseModel):
    draft_id: str | None = Field(default=None, max_length=64)
    spec: dict = Field(default_factory=dict)


class DraftPatchBody(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    spec: dict | None = None
    dataset_version: str | None = Field(default=None, max_length=64)


class DraftReviewBody(BaseModel):
    analysis_version: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=2000)


class DatasetImportBody(BaseModel):
    draft_id: str = Field(min_length=1, max_length=64)
    platform: str = Field(min_length=1, max_length=120)
    filename: str = Field(default="", max_length=255)
    csv: str | None = None
    xlsx_b64: str | None = None
    sheet: str | int | None = None

    @model_validator(mode="after")
    def _need_payload_body(self):
        if not self.csv and not self.xlsx_b64:
            raise ValueError(
                "dataset import needs csv text or xlsx_b64 plus platform")
        return self


class MatchBody(BaseModel):
    creative_key: str = Field(min_length=1, max_length=200)
    method: str = Field(default="manual", max_length=40)
    ad_rowids: list[int] = Field(default_factory=list, max_length=500)


class AnalyzeBody(BaseModel):
    brand_terms: list[str] = Field(default_factory=list, max_length=20)


class ConnectorSheetsBody(BaseModel):
    platform: str = Field(min_length=1, max_length=120)
    url: str = Field(default="", max_length=2000)
    google_auth: bool = False


class ConnectorMetaBody(BaseModel):
    ad_account_id: str = Field(default="", max_length=120)
    since: str = Field(default="", max_length=30)
    until: str = Field(default="", max_length=30)


class ConnectorTikTokBody(BaseModel):
    advertiser_id: str = Field(default="", max_length=120)
    start_date: str = Field(default="", max_length=30)
    end_date: str = Field(default="", max_length=30)


class SyncNowBody(BaseModel):
    source: str = Field(min_length=1, max_length=120)


class RetentionBody(BaseModel):
    creative_key: str = Field(min_length=1, max_length=200)
    points: list[list[float]] = Field(min_length=1, max_length=500)

    @field_validator("points", mode="before")
    @classmethod
    def _check_points(cls, values):
        return _point_pairs(values)


def _point_pairs(values) -> list:
    if not isinstance(values, list) or not values or len(values) > 500:
        raise ValueError("points must be 1-500 [t_sec, pct] pairs")
    out = []
    for pair in values:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("each point must be a [t_sec, pct] pair")
        try:
            out.append([float(pair[0]), float(pair[1])])
        except (TypeError, ValueError):
            raise ValueError("point values must be numbers")
    return out


class SaveViewBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    state: dict = Field(default_factory=dict)

    @field_validator("state", mode="before")
    @classmethod
    def _check_state(cls, values):
        return _bounded_dict(values, what="view state", max_keys=20)


class DeleteViewBody(BaseModel):
    id: int = Field(gt=0, le=2 ** 31)


_DISPATCH_SCHEMAS = {
    "/api/ingest": (IngestBody, "ingest"),
    "/api/media/upload": (MediaUploadJSONBody, "media upload"),
    "/api/connect/drive": (ConnectorSheetsBody, "drive import"),
    "/api/connect/sheets": (ConnectorSheetsBody, "sheets import"),
    "/api/connect/meta": (ConnectorMetaBody, "meta import"),
    "/api/connect/tiktok": (ConnectorTikTokBody, "tiktok import"),
    "/api/sync/run": (SyncNowBody, "sync"),
    "/api/retention": (RetentionBody, "retention points"),
    "/api/views": (SaveViewBody, "view"),
    "/api/views/delete": (DeleteViewBody, "view delete"),
}


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
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="sync_job_created", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="sync_job_created", target=job["id"])
    if not body.enabled:
        job = sync.set_job_enabled(conn, job["id"], False)
    return {"job": job}


def _job_owner_or_403(conn, job_id: str, who) -> dict:
    """Sync jobs are owned: only the owning employee or an admin may
    change, delete or re-target them.

    Without this, any active employee could rewrite another owner's
    sheets/drive job destination, and the scheduled runner would then
    send the OWNER's Google token to the attacker's endpoint.
    """
    job = _job_or_404(conn, job_id)
    if who.id != (job.get("owner_employee_id") or "") \
            and (who.role or "") != "admin":
        raise HTTPException(status_code=403, detail={
            "error": "Only the job owner or an administrator can"
                     " change this sync job.",
            "gate": "forbidden"})
    return job


@router.patch("/api/sync/jobs/{job_id}")
async def sync_job_update(job_id: str, request: Request,
                          conn=Depends(get_product_conn),
                          who=Depends(get_current_employee)):
    from urllib.parse import unquote
    _job_owner_or_403(conn, unquote(job_id), who)
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
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="sync_job_updated",
                             target=unquote(job_id), result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="sync_job_updated", target=unquote(job_id))
    return {"job": sync.get_job(conn, unquote(job_id))}


@router.delete("/api/sync/jobs/{job_id}")
def sync_job_delete(job_id: str, request: Request,
                    conn=Depends(get_product_conn),
                    who=Depends(get_current_employee)):
    from urllib.parse import unquote
    _job_owner_or_403(conn, unquote(job_id), who)
    sync.delete_job(conn, unquote(job_id))
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="sync_job_deleted", target=unquote(job_id))
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
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="sync_started", target=job["id"],
                             result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="sync_started", target=job["id"])
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
    "/api/retention": "retention",
    "/api/views": "save-view",
    "/api/views/delete": "delete-view",
}


@router.post("/api/ask")
async def ask(request: Request, conn=Depends(get_product_conn),
              who=Depends(get_current_employee),
              _limited=Depends(ai_rate_limit)):
    _ = _limited
    body = _validated(AskBody, await json_payload(request), "ask")
    settings = request.app.state.ci_settings
    ctx = {"settings": settings, "media_dir": None}
    try:
        loop = asyncio.get_running_loop()
        out = await loop.run_in_executor(
            _WORKERS, functools.partial(
                jobs_mod.run_through, conn, "ask", body.model_dump(),
                who.id, 180.0, 2.0, ctx))
    except jobs_mod.JobTimeout as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="ask", result="error")
        raise HTTPException(status_code=504, detail={"error": str(exc)})
    except jobs_mod.JobFailed as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="ask", result="error")
        # Managed single-active transport failures surface as 502;
        # paused AI and every legacy failure keep the 409 contract.
        if "[provider=" in str(exc):
            raise _provider_failure(exc)
        raise _conflict(exc)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="ask", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id, action="ask")
    return out


@router.post("/api/analyst/ask")
async def analyst_ask(request: Request, conn=Depends(get_product_conn),
                      who=Depends(get_current_employee),
                      _limited=Depends(ai_rate_limit)):
    _ = _limited
    body = _validated(AnalystBody, await json_payload(request), "analyst")
    settings = request.app.state.ci_settings
    ctx = {"settings": settings, "media_dir": None}
    try:
        loop = asyncio.get_running_loop()
        out = await loop.run_in_executor(
            _WORKERS, functools.partial(
                jobs_mod.run_through, conn, "analyst",
                body.model_dump(), who.id, 180.0, 2.0, ctx))
    except jobs_mod.JobTimeout as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="analyst", result="error")
        raise HTTPException(status_code=504, detail={"error": str(exc)})
    except jobs_mod.JobFailed as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="analyst", result="error")
        raise _conflict(exc)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="analyst", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="analyst")
    return out


class AnalystConversationBody(BaseModel):
    objective: str = "reach"
    language: str | None = None

    @field_validator("objective", mode="before")
    @classmethod
    def _check_objective(cls, value):
        from creative_intel import analyst as analyst_mod
        if value in (None, ""):
            return "reach"
        if value not in analyst_mod.OBJECTIVES:
            raise ValueError(
                "objective must be one of %s"
                % (list(analyst_mod.OBJECTIVES),))
        return value


@router.post("/api/analyst/conversations")
async def analyst_conversation_create(
        request: Request, conn=Depends(get_product_conn),
        who=Depends(get_current_employee)):
    """Start an empty conversation (A04: the page POSTs here)."""
    body = _validated(AnalystConversationBody,
                      await json_payload(request),
                      "analyst conversation")
    try:
        conv_id = analyst_chat.create_conversation(
            conn, who.id, "", {}, body.objective,
            body.language or "en")
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="analyst-conversation")
        return {"id": conv_id}
    except ValueError as exc:
        raise _conflict(exc)


@router.get("/api/analyst/conversations")
def analyst_conversations(conn=Depends(get_product_conn),
                          who=Depends(get_current_employee)):
    try:
        return {"conversations": analyst_chat.list_conversations(
            conn, who.id)}
    except ValueError as exc:
        raise _conflict(exc)


@router.get("/api/analyst/conversations/{conv_id}")
def analyst_conversation(conv_id: str,
                         conn=Depends(get_product_conn),
                         who=Depends(get_current_employee)):
    try:
        conv = analyst_chat.get_conversation(conn, who.id, conv_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    rows = conn.execute(
        "SELECT role, kind, body_text, created_at FROM analyst_messages"
        " WHERE conversation_id=? ORDER BY id", (conv_id,)).fetchall()
    conv["messages"] = [{"role": r[0], "kind": r[1], "text": r[2],
                         "created_at": r[3]} for r in rows]
    return conv


@router.get("/api/analyst/creatives")
def analyst_creatives(request: Request,
                      conn=Depends(get_product_conn),
                      who=Depends(get_current_employee),
                      _limited=Depends(ai_rate_limit)):
    """Per-creative diagnostics cards for the current scope.

    Read-only projection of one deterministic analysis: five-layer
    status, metric values + states, top finding with preserve/change
    and confidence, brand evidence and annotation status. Same scope
    semantics as ask/report via the shared Scope axes.
    """
    _ = (who, _limited)
    from creative_intel import benchmarks as benchmarks_mod
    query = query_multidict(request)
    # "objective" here is the analysis-objective selector (validated
    # against analyst.OBJECTIVES below; unknown values 409), never a
    # campaign-objective scope filter: the caller passes
    # ?objective=<analysis objective>, and parsing it as a scope axis
    # narrowed every response to ads carrying that campaign objective
    # (empty on any dataset without one, including the demo seed).
    scope = benchmarks_mod.Scope.from_query(
        query, ignore=("objective",)).resolve(conn).normalized()
    objective = (query.get("objective") or ["reach"])[0]
    if objective not in analyst.OBJECTIVES:
        raise _conflict(ValueError(
            "objective must be one of %s" % (list(analyst.OBJECTIVES),)))

    # Sync route: FastAPI already runs this off the event loop.
    try:
        analysis = analyst.analyze_campaign(conn, scope, objective)
    except ValueError as exc:
        raise _conflict(exc)
    cards = []
    for creative in analysis.get("creatives", []):
        findings = creative.get("findings", []) or []
        top = findings[0] if findings else {}
        metrics = {}
        for mid, res in (creative.get("metrics") or {}).items():
            if mid == "exposure":
                continue
            metrics[mid] = {"value": (res or {}).get("value"),
                            "state": (res or {}).get("state", ""),
                            "metric_id": (res or {}).get("metric_id",
                                                         mid)}
        cards.append({
            "creative_key": creative.get("creative_key", ""),
            "name": creative.get("name", ""),
            "platform": creative.get("platform", ""),
            "campaign": creative.get("campaign", ""),
            "duration_s": creative.get("duration_s", 0),
            "message_class": creative.get("message_class", "unknown"),
            "format_kind": creative.get("format_kind", "unknown"),
            "opening_delivery": creative.get("opening_delivery",
                                             "unknown"),
            "annotation_status": creative.get("annotation_status",
                                              "unknown"),
            "layers": creative.get("layers", []),
            "metrics": metrics,
            "finding": {
                "primary_signal": top.get("primary_signal", ""),
                "diagnosis": top.get("diagnosis", ""),
                "recommended_iteration": top.get(
                    "recommended_iteration", ""),
                "priority": top.get("priority", ""),
                "confidence_level": top.get("confidence_level", ""),
                "element_to_preserve": top.get("element_to_preserve",
                                               ""),
                "element_to_change": top.get("element_to_change", ""),
                "limitations": top.get("limitations", []) or [],
            } if top else None,
            "brand": creative.get("brand", {}),
        })
    return {"creatives": cards,
            "scope": analysis.get("scope"),
            "dataset_version": analysis.get("dataset_version"),
            "objective": analysis.get("objective")}


@router.get("/api/analyst/workbook")
def analyst_workbook_download(request: Request, conn=Depends(get_product_conn),
                              who=Depends(get_current_employee),
                              _limited=Depends(ai_rate_limit)):
    _ = (conn, who, _limited)
    # Workbook configuration travels as query params so the export
    # reflects the user's name / description / modules / KPIs on a
    # cover sheet. Absent params yield the historical seven-sheet file.
    qp = request.query_params
    name = (qp.get("name") or "")[:120]
    description = (qp.get("description") or "")[:200]
    modules = [m.strip() for m in (qp.get("modules") or "").split(",")
               if m.strip()][:50]
    kpis = [k.strip() for k in (qp.get("kpis") or "").split(",")
            if k.strip()][:50]
    cover = None
    if name or description or modules or kpis:
        cover = {"name": name, "description": description,
                 "modules": modules, "kpis": kpis}
    blob = analyst_workbook.build_blank_workbook(cover=cover)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument"
                   ".spreadsheetml.sheet",
        headers={"Content-Disposition":
                 "attachment; filename=\"foap-analyst-workbook.xlsx\""})


@router.post("/api/analyst/report")
async def analyst_report(request: Request,
                         conn=Depends(get_product_conn),
                         who=Depends(get_current_employee),
                         _limited=Depends(ai_rate_limit)):
    _ = _limited
    body = _validated(AnalystReportBody, await json_payload(request),
                      "analyst report")
    payload = body.model_dump()
    if not payload.get("override"):
        try:
            export_gate.check_reviews(conn)
        except export_gate.ExportBlocked as exc:
            paudit.audit_request(request, conn, employee_id=who.id,
                                 action="analyst-report", result="error")
            raise _conflict(exc)
    def _compute():
        analysis = analyst.analyze_campaign(
            conn, payload.get("scope") or {}, payload.get("objective") or
            "reach")
        return analyst_chat.build_analyst_report(
            analysis, lang=payload.get("language") or "en",
            sections=payload.get("sections") or None,
            rank_by=payload.get("rank_by"))
    try:
        loop = asyncio.get_running_loop()
        report = await loop.run_in_executor(_WORKERS, _compute)
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="analyst-report", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="analyst-report")
    if payload.get("fmt") == "xlsx":
        blob = ooxml.build_xlsx(report["sheets"])
        return Response(
            content=blob,
            media_type="application/vnd.openxmlformats-officedocument"
                       ".spreadsheetml.sheet",
            headers={"Content-Disposition":
                     "attachment; filename=\"foap-analyst-report.xlsx\""})
    return {"format": "one-pager", "markdown": report["markdown"],
            "meta": report["meta"]}


@router.post("/api/analyst/findings/{finding_id}")
async def analyst_finding_status(
        finding_id: str, request: Request,
        conn=Depends(get_product_conn),
        who=Depends(get_current_employee)):
    body = _validated(FindingStatusBody, await json_payload(request),
                      "analyst finding")
    try:
        out = analyst_chat.set_finding_status(conn, who.id, finding_id,
                                              body.status)
    except ValueError as exc:
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="analyst-finding")
    return out


class AnalystBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    # None = scope omitted: inherit the conversation's scope (A20).
    # {} = explicit "All Data": clear to the whole dataset.
    scope: dict | None = None
    objective: str = "reach"
    language: str | None = None
    rank_by: str | None = None
    max_points: int | None = Field(default=None, ge=1, le=10)

    @field_validator("objective", mode="before")
    @classmethod
    def _check_objective(cls, value):
        # Unknown objectives used to silently clamp to reach in the
        # engine; reject them at the boundary instead (A04), so the
        # selector and the analysis can never disagree silently.
        from creative_intel import analyst as analyst_mod
        if value in (None, ""):
            return "reach"
        if value not in analyst_mod.OBJECTIVES:
            raise ValueError(
                "objective must be one of %s"
                % (list(analyst_mod.OBJECTIVES),))
        return value

    @field_validator("scope", mode="before")
    @classmethod
    def _check_scope(cls, values):
        if values is None:
            return None
        from creative_intel import analyst as analyst_mod
        allowed = set(_FILTER_KEYS) | set(analyst_mod.EXTRA_SCOPE_KEYS)
        for key in (values or {}):
            if key not in allowed:
                raise ValueError("analyst.filters has unknown key %r"
                                 % (key,))
        scope = _filter_dict(
            {k: v for k, v in (values or {}).items()
             if k in _FILTER_KEYS}, what="analyst")
        # Analyst extra keys (placement, creator, message_class, ...)
        # ride along under the same shape limits.
        for key in analyst_mod.EXTRA_SCOPE_KEYS:
            if key in (values or {}):
                vals = (values[key] if isinstance(values[key], list)
                        else [values[key]])
                if len(vals) > 50 or any(
                        not isinstance(v, str) or not v or len(v) > 200
                        for v in vals):
                    raise ValueError(
                        "analyst.filters[%r] must be a list of at most"
                        " 50 strings" % key)
                scope[key] = vals
        return scope

    @field_validator("language", mode="before")
    @classmethod
    def _check_language(cls, value):
        if value is None:
            return None
        text = str(value).lower()
        if text not in ("pl", "en"):
            raise ValueError("language must be pl or en")
        return text

    @field_validator("rank_by", mode="before")
    @classmethod
    def _check_rank_by(cls, value):
        if value is None:
            return None
        from creative_intel import analyst_metrics as metrics_mod
        if str(value) not in metrics_mod.METRICS:
            raise ValueError("rank_by must be a known metric_id")
        return str(value)


class FindingStatusBody(BaseModel):
    status: str = Field(min_length=1, max_length=16)


class AnalystReportBody(BaseModel):
    scope: dict = Field(default_factory=dict)
    objective: str = "reach"
    language: str = "en"
    sections: list[str] = Field(default_factory=list)
    fmt: str = "one-pager"
    rank_by: str | None = None
    override: bool = False

    @field_validator("objective", mode="before")
    @classmethod
    def _check_objective(cls, value):
        # Same contract as ask: unknown objectives are rejected at
        # the boundary instead of silently clamped (A04).
        from creative_intel import analyst as analyst_mod
        if value in (None, ""):
            return "reach"
        if value not in analyst_mod.OBJECTIVES:
            raise ValueError(
                "objective must be one of %s"
                % (list(analyst_mod.OBJECTIVES),))
        return value

    @field_validator("sections", mode="before")
    @classmethod
    def _check_sections(cls, values):
        from creative_intel import analyst_chat as chat_mod
        if values is None:
            return []
        unknown = [s for s in values
                   if s not in chat_mod.REPORT_SECTIONS]
        if unknown:
            raise ValueError("unknown report sections: %s"
                             % ", ".join(unknown))
        return list(values)

    @field_validator("fmt", mode="before")
    @classmethod
    def _check_fmt(cls, value):
        if value not in ("one-pager", "xlsx"):
            raise ValueError("fmt must be one-pager or xlsx")
        return value


class PipelineRunBody(BaseModel):
    creative_key: str = Field(default="", max_length=200)
    brand_terms: list[str] = Field(default_factory=list)


@router.post("/api/pipeline/run")
def pipeline_run(body: PipelineRunBody, request: Request,
                 conn=Depends(get_product_conn),
                 who=Depends(get_current_employee),
                 _limited=Depends(ai_rate_limit)):
    _ = (_limited, request)
    if not body.creative_key.strip():
        raise _conflict(ValueError("pipeline needs creative_key"))
    job = jobs_mod.enqueue(
        conn, "pipeline",
        {"creative_key": body.creative_key.strip(),
         "brand_terms": [t for t in body.brand_terms
                         if isinstance(t, str)][:20]},
        owner=who.id)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="pipeline_run", target=job["id"],
                         result="queued")
    return {"job_id": job["id"], "status": job["status"]}


def _visible_job(conn, job_id, who):
    job = jobs_mod.get(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "no such job"})
    if who.role != "admin" and job["owner_employee_id"] != who.id:
        raise HTTPException(status_code=403, detail={
            "error": "Not your job.", "gate": "app"})
    return job


@router.get("/api/pipeline/jobs/{job_id}")
def pipeline_job(job_id: str, request: Request,
                 conn=Depends(get_product_conn),
                 who=Depends(get_current_employee)):
    _ = request
    job = _visible_job(conn, job_id, who)
    return {"job_id": job["id"], "kind": job["kind"],
            "status": job["status"], "progress": job["progress"],
            "result": job["result"], "error": job["error"],
            "attempts": job["attempts"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"]}


@router.post("/api/pipeline/jobs/{job_id}/cancel")
def pipeline_cancel(job_id: str, request: Request,
                    conn=Depends(get_product_conn),
                    who=Depends(get_current_employee)):
    _ = request
    owner = "" if who.role == "admin" else who.id
    job = jobs_mod.cancel(conn, job_id, owner=owner)
    if job is None:
        raise HTTPException(status_code=404, detail={
            "error": "no such job or not yours"})
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="pipeline_cancel", target=job["id"])
    return {"job_id": job["id"], "status": job["status"]}


@router.post("/api/reviews/mark")
async def reviews_mark(request: Request, conn=Depends(get_product_conn),
                       who=Depends(get_current_employee)):
    body = _validated(ReviewsMarkBody, await json_payload(request),
                      "review")
    try:
        pending = qa.mark_reviewed(conn, body.review_id)
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="annotation_verified", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="annotation_verified",
                         target=str(body.review_id))
    return {"ok": True, "pending": pending}


@router.post("/api/export")
async def export(request: Request, conn=Depends(get_product_conn),
                 who=Depends(get_current_employee)):
    body = _validated(ExportBody, await json_payload(request), "export")
    try:
        export_gate.check_reviews(conn)
        result = export_gate.build_one_pager(
            conn, body.creative_keys,
            benchmarks.benchmark(conn, "hook_type"),
            override=body.override)
    except export_gate.ExportBlocked as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="report_exported", result="error")
        raise HTTPException(status_code=409, detail={
            "error": str(exc), "missing": exc.missing})
    except (ValueError, emp.StoreError) as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="report_exported", result="error")
        raise _conflict(exc)
    replay.log(conn, "export", {"creative_keys": body.creative_keys,
                                "override": body.override})
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="report_exported",
                         target=",".join(body.creative_keys))
    return result


# Replay runs in a throwaway database and must never touch live
# provider-backed work: re-firing a logged connect/sync/pipeline entry
# would call real APIs and spend real budget. Only pure-local actions
# replay; the rest are counted as skipped.
_LOCAL_REPLAY_ACTIONS = frozenset({
    "ingest", "retention", "verify", "annotate",
    "save-view", "delete-view"})


@router.post("/api/replay/run")
def replay_run(request: Request, conn=Depends(get_product_conn),
               prov=Depends(get_providers),
               _emp=Depends(get_current_employee)):
    hist = replay.history(conn)
    mem = sqlite3.connect(":memory:")
    schema.init_db(mem)
    n = skipped = 0
    for entry in hist:
        if entry["action"] in ("export", "report-override"):
            continue
        if entry["action"] not in _LOCAL_REPLAY_ACTIONS:
            skipped += 1
            continue
        legacy.apply_action(mem, entry["action"], entry["payload"], prov)
        n += 1
    live = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    replayed = mem.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    mem.close()
    return {"replayed": n, "skipped_provider_actions": skipped,
            "live_ads": live, "replayed_ads": replayed,
            "matches_live": live == replayed}


@router.post("/api/cohorts")
async def save_cohort(request: Request, conn=Depends(get_product_conn),
                      _emp=Depends(get_current_employee)):
    body = _validated(CohortBody, await json_payload(request), "cohort")
    try:
        return cohorts.save_cohort(conn, body.name.strip(),
                                   body.filters)
    except ValueError as exc:
        raise _conflict(exc)


@router.delete("/api/cohorts/{cohort_id}")
def delete_cohort(cohort_id: int, request: Request,
                  conn=Depends(get_product_conn),
                  who=Depends(get_current_admin)):
    """Delete a saved benchmark cohort (admin only, audited).

    Non-admin employees get 403 from the admin guard; unknown ids
    get 404. The row is removed from SQLite so the cohort stays
    deleted across refreshes.
    """
    try:
        out = cohorts.delete_cohort(conn, cohort_id=cohort_id)
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="cohort-deleted",
                             target=str(cohort_id), result="error")
        if "unknown cohort" in str(exc):
            raise HTTPException(status_code=404,
                                detail={"error": str(exc)})
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="cohort-deleted", target=str(cohort_id))
    return out


@router.post("/api/compare/campaigns")
async def compare_campaigns_post(request: Request,
                                 conn=Depends(get_product_conn),
                                 _emp=Depends(get_current_employee)):
    body = _validated(CompareBody, await json_payload(request),
                      "campaign comparison")
    try:
        pseudo = {"campaigns": [",".join(body.campaigns)],
                  "rank_by": [body.rank_by]}
        for key, vals in body.filters.items():
            pseudo[key] = (list(vals) if isinstance(vals, list) else [vals])
        return legacy.expert2_compare_route(conn, pseudo)
    except ValueError as exc:
        raise _conflict(exc)


@router.post("/api/report")
async def report(request: Request, conn=Depends(get_product_conn),
                 who=Depends(get_current_employee)):
    body = _validated(ReportBody, await json_payload(request), "report")
    payload = body.model_dump()
    try:
        out = legacy.expert2_report_route(conn, payload)
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="report_generated", result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="report_generated")
    return out


@router.post("/api/creatives/{key}/verify")
async def creative_verify(key: str, request: Request,
                          conn=Depends(get_product_conn),
                          prov=Depends(get_providers),
                          who=Depends(get_current_employee)):
    return await _run_action(conn, prov, "verify", {"creative_key": unquote(key)},
                             actor=who.id, request=request)


@router.post("/api/creatives/{key}/annotate")
async def creative_annotate(key: str, request: Request,
                            conn=Depends(get_product_conn),
                            prov=Depends(get_providers),
                            who=Depends(get_current_employee)):
    body = _validated(AnnotateBody, await json_payload(request),
                      "annotation")
    return await _run_action(conn, prov, "annotate",
                             {"creative_key": unquote(key),
                              "annotation": body.annotation},
                             actor=who.id, request=request)


# ---------------------------------------------------------------------------
# Guided video-upload flow: drafts, validation, datasets, matches
# ---------------------------------------------------------------------------
#
# Writes are owner-or-admin (mirrors the sync-job guard: without it
# any active employee could rewrite another owner's draft, dataset
# link, or confirmed match). Reads follow the media convention (any
# active employee). Draft creation is idempotent on client-supplied
# draft_id so retries and double clicks never duplicate drafts.


def _draft_or_404(conn, draft_id: str) -> dict:
    from creative_intel import drafts as drafts_mod
    draft = drafts_mod.get_draft(conn, draft_id)
    if draft is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Unknown upload draft."})
    return draft


def _draft_owner_or_403(conn, draft_id: str, who) -> dict:
    draft = _draft_or_404(conn, draft_id)
    if who.id != (draft.get("owner_employee_id") or "") \
            and (who.role or "") != "admin":
        raise HTTPException(status_code=403, detail={
            "error": "Only the draft owner or an administrator can"
                     " change this upload draft.",
            "gate": "forbidden"})
    return draft


def _draft_live_job_id(conn, draft_id: str):
    """Id of a queued/running video_analysis job bound to this draft,
    if any (lets clients offer Cancel without a second lookup)."""
    import json as _json
    try:
        rows = conn.execute(
            "SELECT id, payload_json FROM worker_jobs WHERE kind = ?"
            " AND status IN ('queued', 'running')",
            ("video_analysis",)).fetchall()
    except Exception:
        return ""
    for job_id, payload_json in rows:
        try:
            payload = _json.loads(payload_json or "{}")
        except ValueError:
            continue
        if (payload.get("snapshot") or {}).get("draft_id") == draft_id:
            return job_id
    return ""


def _invalidate_draft_review(conn, did: str) -> None:
    """Drop a draft's recorded human review after a material input
    change, and return this draft's still-bound video keys from
    human_verified to auto: the approval belonged to the old inputs.
    Annotations of videos already unbound from the draft (replaced
    away) keep their history — they are no longer this draft's
    claim."""
    from creative_intel import drafts as drafts_mod
    from creative_intel import creative as creative_mod
    import json as _json
    drafts_mod.clear_review(conn, did)
    keys = {v.get("creative_key")
            for v in drafts_mod.list_videos(conn, did)
            if v.get("creative_key")}
    for key in keys:
        row = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (key,)).fetchone()
        if not row:
            continue
        try:
            ann = _json.loads(row[0])
        except ValueError:
            continue
        if isinstance(ann, dict) and ann.get("status") == "human_verified":
            ann["status"] = "auto"
            try:
                creative_mod.save_annotation(conn, key, ann)
            except ValueError:
                pass


def _draft_view(conn, draft: dict) -> dict:
    from creative_intel import drafts as drafts_mod
    import json as _json
    out = dict(draft)
    try:
        out["spec"] = _json.loads(draft.get("spec_json") or "{}")
    except ValueError:
        out["spec"] = {}
    out.pop("spec_json", None)
    try:
        review = _json.loads(draft.get("review_json") or "{}")
        out["review"] = review if isinstance(review, dict) else {}
    except ValueError:
        out["review"] = {}
    out.pop("review_json", None)
    out["videos"] = drafts_mod.list_videos(conn, draft["id"])
    out["datasets"] = drafts_mod.list_datasets(conn, draft["id"])
    cur = conn.execute("SELECT * FROM matches WHERE draft_id = ?",
                       (draft["id"],))
    cols = [d[0] for d in cur.description]
    out["matches"] = [dict(zip(cols, row)) for row in cur.fetchall()]
    out["live_job_id"] = _draft_live_job_id(conn, draft["id"])
    return out


@router.get("/api/videos/limits")
def video_limits(_emp=Depends(get_current_employee)):
    from creative_intel import video_validate
    return video_validate.limits()


@router.post("/api/videos/validate")
async def video_validate(request: Request,
                         conn=Depends(get_product_conn),
                         who=Depends(get_current_employee)):
    from creative_intel import drafts as drafts_mod
    from creative_intel import video_validate
    from ci_backend import actions as legacy
    check_user_limit(request, who.id, *UPLOAD_RATE_LIMIT, "upload")
    try:
        body = VideoValidateBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid validation: %s" % exc})
    try:
        info = media.describe(conn, legacy._media_dir(), body.media_id)
        path = media.file_path(conn, legacy._media_dir(), body.media_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    loop = asyncio.get_running_loop()
    verdict = await loop.run_in_executor(
        _WORKERS, functools.partial(video_validate.validate, path,
                                    info.get("filename", "")))
    # The media library is tenant-shared (reads are open to any
    # active employee, same as GET /media/{id}): attribution lives
    # on the draft, so every validated video is bound to a draft
    # the caller owns. Without a draft_id we mint a caller-owned
    # draft instead of leaving an orphan video row.
    draft_id = body.draft_id
    if draft_id:
        _draft_owner_or_403(conn, draft_id, who)
    elif verdict["status"] == "valid":
        draft_id = drafts_mod.create_draft(conn, who.id)
    creative_key = ""
    if verdict["status"] == "valid":
        try:
            row = conn.execute(
                "SELECT creative_key, sha256 FROM media WHERE id = ?",
                (body.media_id,)).fetchone()
            creative_key = row[0] if row else ""
            # Replacement, not history: the newly validated video
            # becomes the draft's single active version, so analysis
            # can never bind an older row while the form shows the
            # new one. (An invalid verdict leaves the prior valid
            # video untouched.)
            drafts_mod.clear_videos(conn, draft_id)
            vid = drafts_mod.add_video(
                conn, draft_id, creative_key,
                media_id=body.media_id, duration_s=verdict["duration_s"],
                width=verdict["width"], height=verdict["height"],
                sha256=row[1] if row else "",
                validation=verdict)
            # A new video version invalidates any prior confirmation,
            # same as a spec or dataset edit.
            drafts_mod.clear_matches(conn, draft_id)
            _invalidate_draft_review(conn, draft_id)
        except ValueError as exc:
            raise _conflict(exc)
    else:
        vid = ""
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="video_validated",
                         target=creative_key or str(body.media_id),
                         result="ok" if vid else "error")
    return {"video_id": vid, "media_id": body.media_id,
            "draft_id": draft_id,
            "creative_key": creative_key,
            "duration_s": verdict["duration_s"],
            "width": verdict["width"], "height": verdict["height"],
            "validation": verdict}


@router.post("/api/drafts")
async def draft_create(request: Request, conn=Depends(get_product_conn),
                       who=Depends(get_current_employee)):
    from creative_intel import drafts as drafts_mod
    try:
        body = DraftCreateBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid draft: %s" % exc})
    try:
        did = drafts_mod.create_draft(conn, who.id,
                                      draft_id=body.draft_id or None,
                                      spec=body.spec)
    except ValueError as exc:
        raise _conflict(exc)
    draft = _draft_or_404(conn, did)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_created", target=did)
    return {"draft": _draft_view(conn, draft)}


@router.get("/api/drafts")
def draft_list(request: Request, conn=Depends(get_product_conn),
               who=Depends(get_current_employee)):
    from creative_intel import drafts as drafts_mod
    _ = request
    return {"drafts": [_draft_view(conn, d) for d in
                       drafts_mod.list_drafts(conn, who.id)]}


@router.get("/api/drafts/{draft_id}")
def draft_get(draft_id: str, request: Request,
              conn=Depends(get_product_conn),
              who=Depends(get_current_employee)):
    from urllib.parse import unquote
    _ = request
    # Owner-or-admin like writes: the view carries matched
    # performance records and analysis, which must not leak across
    # employees (the media library stays shared-tenant; attribution
    # lives on the draft).
    return {"draft": _draft_view(
        conn, _draft_owner_or_403(conn, unquote(draft_id), who))}


@router.patch("/api/drafts/{draft_id}")
async def draft_patch(draft_id: str, request: Request,
                      conn=Depends(get_product_conn),
                      who=Depends(get_current_employee)):
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    did = unquote(draft_id)
    _draft_owner_or_403(conn, did, who)
    try:
        body = DraftPatchBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid draft: %s" % exc})
    if body.status in drafts_mod.WORKER_MIRRORED_STATUSES:
        # Pipeline state is worker-mirrored: a client setting it
        # would forge analysis progress around the worker and its
        # staleness guard. Submit/cancel flow through /analyze and
        # the job-cancel endpoint instead.
        raise HTTPException(status_code=409, detail={
            "error": "Draft status %r is set by the analysis pipeline,"
                     " not by clients." % body.status})
    if body.status == "reviewed":
        # Reviewed is a recorded verdict (reviewer + analysis
        # version), never a free status flip: approving an empty or
        # stale draft must go through the review operation below.
        raise HTTPException(status_code=409, detail={
            "error": "Mark a draft reviewed with POST"
                     " /api/drafts/{id}/review, not PATCH."})
    try:
        ok = drafts_mod.update_draft(conn, did, status=body.status,
                                     spec=body.spec,
                                     dataset_version=body.dataset_version)
    except ValueError as exc:
        raise _conflict(exc)
    if not ok:
        raise HTTPException(status_code=404,
                            detail={"error": "Unknown upload draft."})
    if body.spec is not None or body.dataset_version is not None:
        # Material input change invalidates any prior confirmation
        # and its dependent review (caller re-confirms afterwards).
        drafts_mod.clear_matches(conn, did)
        _invalidate_draft_review(conn, did)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_updated", target=did)
    return {"draft": _draft_view(conn, _draft_or_404(conn, did))}


@router.delete("/api/drafts/{draft_id}")
def draft_delete(draft_id: str, request: Request,
                 conn=Depends(get_product_conn),
                 who=Depends(get_current_employee)):
    from urllib.parse import unquote
    from creative_intel import jobs as jobs_mod
    from creative_intel import drafts as drafts_mod
    from creative_intel import media as media_mod
    from ci_backend import actions as legacy
    did = unquote(draft_id)
    _draft_owner_or_403(conn, did, who)
    # Content lifecycle: collect this draft's media/keys first. After
    # the workflow rows go, unreferenced assets are erased (media row
    # + stored file, annotation); anything still referenced by
    # another draft's videos is kept. Transcripts stay on the shared
    # creatives rows, which are reporting facts, not draft content.
    doomed_media = {v.get("media_id") for v in
                    drafts_mod.list_videos(conn, did)
                    if v.get("media_id")}
    doomed_keys = {v.get("creative_key") for v in
                   drafts_mod.list_videos(conn, did)
                   if v.get("creative_key")}
    # Cancel every queued/running analysis bound to this draft
    # first so no orphan worker job later mirrors status onto a
    # gone draft (its staleness guard would drop the write, but
    # the job row would linger as queued/running forever).
    import json as _json
    owner = "" if (who.role or "") == "admin" else who.id
    try:
        bound = conn.execute(
            "SELECT id, payload_json FROM worker_jobs WHERE kind = ?"
            " AND status IN ('queued', 'running')",
            ("video_analysis",)).fetchall()
    except Exception:
        bound = []
    for job_id, payload_json in bound:
        try:
            payload = _json.loads(payload_json or "{}")
        except ValueError:
            continue
        if (payload.get("snapshot") or {}).get("draft_id") == did:
            jobs_mod.cancel(conn, job_id, owner=owner)
    for table in ("matches", "videos", "datasets"):
        conn.execute("DELETE FROM %s WHERE draft_id = ?" % table, (did,))
    conn.execute("DELETE FROM drafts WHERE id = ?", (did,))
    conn.commit()
    store = legacy._media_dir()
    for mid in sorted(doomed_media):
        still = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE media_id = ?",
            (mid,)).fetchone()[0]
        if not still:
            try:
                media_mod.delete_media(conn, store, mid)
            except ValueError:
                pass
    for key in sorted(doomed_keys):
        still = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE creative_key = ?",
            (key,)).fetchone()[0]
        if not still:
            conn.execute("DELETE FROM annotations WHERE creative_key=?",
                         (key,))
    conn.commit()
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_deleted", target=did)
    return {"ok": True}


@router.delete("/api/drafts/{draft_id}/videos")
def draft_videos_delete(draft_id: str, request: Request,
                        conn=Depends(get_product_conn),
                        who=Depends(get_current_employee)):
    """Explicit video removal: drops the draft's bound video row(s)
    so a removed video can never resurrect from the relationship on
    reopen. Clearing the form alone is not removal."""
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    did = unquote(draft_id)
    _draft_owner_or_403(conn, did, who)
    removed = drafts_mod.clear_videos(conn, did)
    # A removed video invalidates any prior confirmation like any
    # other material input change.
    drafts_mod.clear_matches(conn, did)
    _invalidate_draft_review(conn, did)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_video_removed", target=did)
    return {"ok": True, "removed": removed}


@router.post("/api/datasets/import")
async def dataset_import(request: Request, conn=Depends(get_product_conn),
                         who=Depends(get_current_employee)):
    from creative_intel import drafts as drafts_mod
    from creative_intel import ingest
    check_user_limit(request, who.id, *UPLOAD_RATE_LIMIT, "upload")
    try:
        body = DatasetImportBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid dataset: %s" % exc})
    _draft_owner_or_403(conn, body.draft_id, who)
    try:
        if body.xlsx_b64:
            import base64
            try:
                blob = base64.b64decode(body.xlsx_b64, validate=True)
            except Exception:
                raise ValueError("xlsx_b64 is not valid base64")
            result = ingest.import_xlsx_report(
                conn, blob, body.platform, source="upload",
                filename=body.filename or "", imported_by=who.id,
                sheet=body.sheet)
        else:
            result = ingest.import_report(
                conn, body.csv or "", body.platform, source="upload",
                filename=body.filename or "", imported_by=who.id)
    except ingest.AmbiguousSheet as exc:
        raise HTTPException(status_code=409, detail={
            "error": str(exc), "sheets": exc.sheets})
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="dataset_imported",
                             target=body.draft_id, result="error")
        raise _conflict(exc)
    dsid = drafts_mod.add_dataset(
        conn, body.draft_id, body.filename or "",
        rows=result["inserted"] + result["updated"],
        version=result["import_id"])
    drafts_mod.update_draft(conn, body.draft_id,
                            dataset_version=result["import_id"])
    # New input invalidates any prior confirmation.
    drafts_mod.clear_matches(conn, body.draft_id)
    _invalidate_draft_review(conn, body.draft_id)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="dataset_imported", target=dsid)
    return {"dataset_id": dsid, "draft_id": body.draft_id,
            "rows": result["inserted"] + result["updated"],
            "version": result["import_id"],
            "inserted": result["inserted"], "updated": result["updated"],
            "quarantined": result["quarantined"],
            "quarantine": result["quarantine"],
            "sheet": result.get("sheet", ""),
            "sheets": result.get("sheets", [])}


_MATCH_COLUMNS = ("id", "import_id", "platform", "campaign", "adset",
                  "ad_name", "creative_key", "spend", "impressions",
                  "clicks", "link_clicks", "conversions", "video_views",
                  "views_25", "views_50", "views_75", "views_100",
                  "currency", "date", "client", "placement",
                  "missing_json")


def _match_records(conn, draft: dict, ad_rowids) -> list:
    """Load frozen snapshots of the submitted ads rows, verifying
    each one belongs to the draft's imported dataset version.
    Browser-submitted identifiers are never trusted on their own."""
    import json as _json
    try:
        wanted = [int(r) for r in (ad_rowids or [])]
    except (TypeError, ValueError):
        raise ValueError("ad_rowids must be ads row ids")
    if not wanted:
        raise ValueError("confirm at least one performance record")
    version = draft.get("dataset_version") or ""
    if not version:
        raise ValueError("import performance data before matching")
    cols = ", ".join(_MATCH_COLUMNS)
    found = conn.execute(
        "SELECT %s FROM ads WHERE id IN (%s)"
        % (cols, ",".join("?" * len(wanted))), wanted).fetchall()
    by_id = {row[0]: dict(zip(_MATCH_COLUMNS, row)) for row in found}
    missing = [r for r in wanted if r not in by_id]
    if missing:
        raise ValueError("unknown performance records: %s" % missing[:5])
    foreign = [r for r, snap in by_id.items()
               if (snap.get("import_id") or "") != version]
    if foreign:
        raise ValueError("records %s are not from this draft's dataset"
                         % foreign[:5])
    return [_json.loads(_json.dumps(by_id[r], default=str))
            for r in wanted]


def _require_campaign_scope(draft: dict, records: list) -> None:
    """When the draft's client/campaign selection is confirmed, every
    matched record must belong to that campaign. Without this, a
    Client A selection could confirm Client B rows and the analysis
    would attribute foreign performance to the video. (Unconfirmed
    selections stay permissive so exploration is never blocked; the
    report carries no client grain, so only campaign is enforceable
    — client scoping is documented, not faked.)"""
    import json as _json
    try:
        spec = _json.loads(draft.get("spec_json") or "{}")
    except ValueError:
        spec = {}
    if not spec.get("clientConfirmed"):
        return
    campaign = (spec.get("campaign") or "").strip()
    if not campaign:
        return
    foreign = [r.get("id") for r in (records or [])
               if (r.get("campaign") or "").strip() != campaign]
    if foreign:
        raise ValueError(
            "records %s are not in the confirmed campaign %r"
            % (foreign[:5], campaign))


def _valid_video_keys(conn, draft_id: str) -> set:
    """Creative keys of this draft's validated videos. Match keys
    must come from this set: it binds a confirmation to the video
    the user actually uploaded, not an arbitrary string."""
    from creative_intel import drafts as drafts_mod
    import json as _json
    keys = set()
    for video in drafts_mod.list_videos(conn, draft_id):
        try:
            verdict = _json.loads(video.get("validation_json") or "{}")
        except ValueError:
            continue
        if verdict.get("status") == "valid" and video.get("creative_key"):
            keys.add(video["creative_key"])
    return keys


@router.post("/api/drafts/{draft_id}/matches/propose")
async def match_propose(draft_id: str, request: Request,
                        conn=Depends(get_product_conn),
                        who=Depends(get_current_employee)):
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    did = unquote(draft_id)
    _draft_owner_or_403(conn, did, who)
    try:
        body = MatchBody.model_validate(await json_payload(request))
        if body.creative_key not in _valid_video_keys(conn, did):
            raise ValueError("match key must be a validated video on this draft")
        records = _match_records(conn, _draft_or_404(conn, did),
                                 body.ad_rowids)
        _require_campaign_scope(_draft_or_404(conn, did), records)
        drafts_mod.propose_match(conn, did, body.creative_key,
                                 body.method, records)
    except ValueError as exc:
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="match_proposed", target=did)
    return {"match": drafts_mod.get_match(conn, did, body.creative_key)}


@router.post("/api/drafts/{draft_id}/matches/confirm")
async def match_confirm(draft_id: str, request: Request,
                        conn=Depends(get_product_conn),
                        who=Depends(get_current_employee)):
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    did = unquote(draft_id)
    draft = _draft_owner_or_403(conn, did, who)
    try:
        body = MatchBody.model_validate(await json_payload(request))
        records = _match_records(conn, draft, body.ad_rowids)
        _require_campaign_scope(draft, records)
        valid_keys = _valid_video_keys(conn, did)
        if not valid_keys:
            raise ValueError("validate the video before confirming")
        if body.creative_key not in valid_keys:
            raise ValueError("match key must be a validated video on this draft")
        drafts_mod.confirm_match(conn, did, body.creative_key, who.id,
                                 method=body.method, records=records)
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="match_confirmed", target=did,
                             result="error")
        raise _conflict(exc)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="match_confirmed", target=did)
    return {"match": drafts_mod.get_match(conn, did, body.creative_key)}


@router.post("/api/drafts/{draft_id}/review")
async def draft_review(draft_id: str, request: Request,
                       conn=Depends(get_product_conn),
                       who=Depends(get_current_employee)):
    """Record a human review of the current analysis version.

    Genuine review operation, not a status flip: the draft must be
    ready_for_review and the submitted analysis_version must equal
    the stored analysis block's version, binding the approval to
    exactly what the reviewer saw (reviewer identity, timestamp,
    and note are recorded). Any later material input change
    invalidates it via _invalidate_draft_review.
    """
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    import json as _json
    did = unquote(draft_id)
    draft = _draft_owner_or_403(conn, did, who)
    try:
        body = DraftReviewBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid review: %s" % exc})
    if (draft.get("status") or "") != "ready_for_review":
        raise HTTPException(status_code=409, detail={
            "error": "Only a draft ready for review can be reviewed"
                     " (status is %r)." % (draft.get("status") or "")})
    videos = drafts_mod.list_videos(conn, did)
    key = videos[0]["creative_key"] if videos else ""
    current = ""
    if key:
        row = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (key,)).fetchone()
        if row:
            try:
                current = (_json.loads(row[0]).get("analysis") or {}) \
                    .get("version", "")
            except ValueError:
                current = ""
    if not current:
        raise HTTPException(status_code=409, detail={
            "error": "No stored analysis to review yet."})
    if body.analysis_version != current:
        raise HTTPException(status_code=409, detail={
            "error": "Analysis version %r is not current (%r): re-read "
                     "the findings before reviewing."
            % (body.analysis_version, current)})
    review = drafts_mod.set_review(conn, did, who.id, current,
                                   note=body.note)
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_reviewed", target=did)
    return {"draft": _draft_view(conn, _draft_or_404(conn, did)),
            "review": review}


def _draft_live_job(conn, draft_id: str):
    """A queued/running video_analysis job already bound to this draft."""
    return _draft_live_job_id(conn, draft_id) or None


@router.post("/api/drafts/{draft_id}/analyze")
async def draft_analyze(draft_id: str, request: Request,
                        conn=Depends(get_product_conn),
                        who=Depends(get_current_employee),
                        _limited=Depends(ai_rate_limit)):
    from urllib.parse import unquote
    from creative_intel import drafts as drafts_mod
    from creative_intel import video_analysis
    _ = _limited
    did = unquote(draft_id)
    _draft_owner_or_403(conn, did, who)
    try:
        body = AnalyzeBody.model_validate(await json_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid analyse: %s" % exc})
    live = _draft_live_job(conn, did)
    if live:
        raise HTTPException(status_code=409, detail={
            "error": "analysis already running for this draft",
            "job_id": live})
    try:
        snapshot = video_analysis.bind_snapshot(conn, did)
    except video_analysis.AnalysisUnavailable as exc:
        raise HTTPException(status_code=409,
                            detail={"error": str(exc)})
    ready = video_analysis.readiness()
    if not ready["ready"]:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="draft_analyzed", target=did,
                             result="error")
        raise HTTPException(status_code=409, detail={
            "error": ready["reason"], "sends": ready["sends"],
            "storage": ready["storage"]})
    job = jobs_mod.enqueue(
        conn, "video_analysis",
        {"snapshot": snapshot,
         "brand_terms": [t for t in body.brand_terms
                         if isinstance(t, str)][:20]},
        owner=who.id)
    # Submitted as queued; the worker flips to analyzing when work
    # actually starts (and to ready_for_review / failed / cancelled
    # on the way out), so the status is never a lie.
    drafts_mod.update_draft(conn, did, status="queued")
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="draft_analyzed", target=job["id"])
    return {"job_id": job["id"], "status": job["status"],
            "draft_id": did, "model": ready["model"],
            "provider": ready["provider"], "sends": ready["sends"],
            "storage": ready["storage"],
            "poll": "/api/pipeline/jobs/%s" % job["id"]}


@router.get("/api/drafts/{draft_id}/analysis")
def draft_analysis(draft_id: str, request: Request,
                   conn=Depends(get_product_conn),
                   who=Depends(get_current_employee)):
    from urllib.parse import unquote
    import json as _json
    _ = request
    draft = _draft_owner_or_403(conn, unquote(draft_id), who)
    videos = _draft_view(conn, draft)["videos"]
    key = videos[0]["creative_key"] if videos else ""
    annotation, transcript = None, ""
    if key:
        row = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (key,)).fetchone()
        if row:
            try:
                annotation = _json.loads(row[0])
            except ValueError:
                annotation = None
        trow = conn.execute("SELECT transcript FROM creatives"
                            " WHERE creative_key=?", (key,)).fetchone()
        transcript = trow[0] if trow else ""
    return {"draft_id": draft["id"], "status": draft["status"],
            "creative_key": key, "annotation": annotation,
            "transcript": transcript}


@router.get("/api/drafts/{draft_id}/candidates")
def draft_candidates(draft_id: str, request: Request,
                     conn=Depends(get_product_conn),
                     who=Depends(get_current_employee)):
    """Matchable performance rows for this draft's dataset version.

    Read-only and scoped: only rows from the draft's imported
    dataset_version are listed (capped), so the browser picks real
    row ids instead of inventing them. Owner-or-admin like every
    other draft read: candidates are the draft's private data.
    """
    from urllib.parse import unquote
    _ = request
    draft = _draft_owner_or_403(conn, unquote(draft_id), who)
    version = draft.get("dataset_version") or ""
    if not version:
        return {"candidates": [], "version": ""}
    cols = ", ".join(_MATCH_COLUMNS)
    cur = conn.execute(
        "SELECT %s FROM ads WHERE import_id = ? ORDER BY id LIMIT 200"
        % cols, (version,))
    names = [d[0] for d in cur.description]
    return {"candidates": [dict(zip(names, row))
                           for row in cur.fetchall()],
            "version": version}


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
        return await _media_upload_multipart(request, conn, who)
    # Cost guard first: rate limits apply before schema validation so
    # malformed bodies cannot burn provider budget limit-free.
    _route_limits(request, _ACTION_ROUTES[path], who.id)
    raw = await json_payload(request)
    schema = _DISPATCH_SCHEMAS.get(path)
    body = (_validated(schema[0], raw, schema[1]) if schema is not None
            else raw)
    payload = (body.model_dump() if isinstance(body, BaseModel) else body)
    return await _run_action(conn, prov, _ACTION_ROUTES[path], payload,
                             actor=who.id, request=request,
                             limits_checked=True)


async def _media_upload_multipart(request: Request, conn, who):
    """Multipart creative upload: bytes ride outside JSON.

    Genuinely streaming: chunks flow straight to a temp file in the
    media store while bytes are counted and hashed, so a 100 MB video
    never sits whole in server RAM. Magic/MIME validation reads only
    the head; the temp file is then atomically renamed into place.
    """
    import hashlib
    import tempfile

    check_user_limit(request, who.id, *UPLOAD_RATE_LIMIT, "upload")
    try:
        form = await request.form()
    except Exception:
        raise HTTPException(status_code=409,
                            detail={"error": "upload needs multipart form"})
    async def _close_parts():
        # Starlette parks each file part in a SpooledTemporaryFile that
        # nothing else closes: release every part on every exit path,
        # including validation rejections before streaming starts.
        for part in form.values():
            close = getattr(part, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass

    creative_key = form.get("creative_key") or ""
    upload = form.get("file")
    read = getattr(upload, "read", None)
    filename = getattr(upload, "filename", "") or ""
    if not creative_key or read is None or not filename:
        await _close_parts()
        raise HTTPException(
            status_code=409,
            detail={"error": "upload needs creative_key and a file part"})
    store = legacy._media_dir()
    os.makedirs(store, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=store, prefix=".upload-")
    digest, total = hashlib.sha256(), 0
    target = str(creative_key)[:200]
    try:
        with os.fdopen(fd, "wb") as fh:
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
                digest.update(piece)
                fh.write(piece)
        out = media.save_media_file(
            conn, store, creative_key, filename, tmp_path, total,
            digest.hexdigest(),
            getattr(upload, "content_type", None) or None)
    except HTTPException:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="creative_uploaded", target=target,
                             result="error")
        raise
    except ValueError as exc:
        paudit.audit_request(request, conn, employee_id=who.id,
                             action="creative_uploaded", target=target,
                             result="error")
        raise _conflict(exc)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        await _close_parts()
    paudit.audit_request(request, conn, employee_id=who.id,
                         action="creative_uploaded", target=target)
    return out


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


# Product writes worth an audit row: uploads, annotation checks,
# sync starts and connector changes. Targets stay metadata (keys,
# action names); payloads (annotations, tokens, file bytes) never do.
_AUDITED_ACTIONS = {
    "verify": "annotation_verified",
    "annotate": "creative_annotated",
    "media-upload": "creative_uploaded",
    "sync-now": "sync_started",
    "connect-sheets": "connector_changed",
    "connect-drive": "connector_changed",
    "connect-meta": "connector_changed",
    "connect-tiktok": "connector_changed",
}


def _audit_target(action: str, payload: dict) -> str:
    if action in ("verify", "annotate", "media-upload"):
        key = payload.get("creative_key", "") if isinstance(
            payload, dict) else ""
        return str(key)[:200]
    if action.startswith("connect-"):
        return action
    return ""


def _route_limits(request, action: str, actor: str) -> None:
    """Per-user cost guards for sync/connector runs and uploads."""
    if request is not None and action in (
            "sync-now", "connect-sheets", "connect-drive",
            "connect-meta", "connect-tiktok"):
        check_user_limit(request, actor, *SYNC_RATE_LIMIT, "sync")
    if request is not None and action == "media-upload":
        check_user_limit(request, actor, *UPLOAD_RATE_LIMIT, "upload")


async def _run_action(conn, prov, action: str, payload: dict, actor: str = "",
                      request=None, limits_checked=False):
    """Run one product action without blocking the event loop.

    Video/AI work (pipeline, imports, media) is synchronous blocking
    code by design, so it hops to a worker thread; the loop stays free
    for health, auth, and other requests. The product SQLite handle
    is single-owner per request (check_same_thread=False) and the
    replay log stays on the loop thread after the hop.
    """
    if action in ("connect-sheets", "connect-drive") and request is not None:
        _resolve_google_bearer(payload, actor, request)
    if not limits_checked:
        _route_limits(request, action, actor)
    audit_name = _AUDITED_ACTIONS.get(action)
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            _WORKERS, functools.partial(legacy.apply_action, conn, action,
                                        payload, prov, actor=actor))
    except (ValueError, export_gate.ExportBlocked, emp.StoreError) as exc:
        if audit_name is not None and request is not None:
            paudit.audit_request(request, conn, employee_id=actor,
                                 action=audit_name,
                                 target=_audit_target(action, payload),
                                 result="error")
        raise _conflict(exc)
    except providers_mod.ProviderUnavailable as exc:
        # Pipeline/verify stages have no rule fallback: paused AI is
        # a 409, a chosen-model transport failure a 502 (previously
        # an unmapped 500).
        if audit_name is not None and request is not None:
            paudit.audit_request(request, conn, employee_id=actor,
                                 action=audit_name,
                                 target=_audit_target(action, payload),
                                 result="error")
        raise _provider_failure(exc)
    finally:
        if isinstance(payload, dict):
            payload.pop("_google_bearer", None)
    if action != "media-upload":
        replay.log(conn, action, payload)
    if audit_name is not None and request is not None:
        paudit.audit_request(request, conn, employee_id=actor,
                             action=audit_name,
                             target=_audit_target(action, payload))
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


@router.get("/api/creatives/{key}/thumbnail")
def creative_thumbnail(key: str, request: Request,
                       conn=Depends(get_product_conn),
                       _emp=Depends(get_current_employee)):
    # Authenticated employees only: creative names are account data.
    # Uploaded media wins; generated sample art covers creatives
    # without uploads; unknown creatives 404 so cards keep the
    # gradient fallback.
    _ = request
    try:
        from ci_backend import actions as legacy
        store = legacy._media_dir()
    except Exception:
        store = ""
    try:
        url = thumbnails.uploaded_image_url(conn, store, key)
        if url is not None:
            return RedirectResponse(url, status_code=302)
        svg = thumbnails.for_creative(conn, key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    if svg is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Unknown creative."})
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "private, no-store"})


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
                        headers={"Cache-Control": "private, no-store"})


_ALLOWED_ASSET_EXTS = (".png", ".svg", ".ico", ".webp")
# Hashed Vite build assets: safe to cache immutably, served from the
# React dist directory only (never from the legacy tree). Image
# extensions cover hashed `import` assets (e.g. provider logos).
_ALLOWED_DIST_EXTS = (".js", ".css", ".woff2", ".png", ".svg", ".webp",
                      ".jpg", ".jpeg", ".gif")


_INLINE_SCRIPT_RE = re.compile(rb"<script>(.*?)</script>", re.DOTALL)
_INDEX_CSP_CACHE: dict = {}


def _react_csp(entry: str) -> dict:
    """Strict CSP for the React entry, with sha256 hashes for its bare
    inline scripts (currently only the pre-render theme boot: the only
    inline script the build ships). Per CSP fallback the hashes live in
    default-src, so no script-src directive is needed and the policy is
    never loosened to 'unsafe-inline'. External module scripts stay
    covered by 'self'; the hashes are recomputed when the file changes,
    so rebuilds need no code edit."""
    try:
        mtime = os.path.getmtime(entry)
    except OSError:
        mtime = -1
    cached = _INDEX_CSP_CACHE.get(entry)
    if cached and cached[0] == mtime:
        return cached[1]
    hashes = []
    try:
        with open(entry, "rb") as fh:
            html = fh.read()
        for body in _INLINE_SCRIPT_RE.findall(html):
            digest = hashlib.sha256(body).digest()
            hashes.append("'sha256-%s'"
                          % base64.b64encode(digest).decode("ascii"))
    except OSError:
        hashes = []
    headers = {"Content-Security-Policy":
               "default-src 'self'%s; "
               "img-src 'self' data: https:; "
               "style-src 'self' 'unsafe-inline'"
               % (" " + " ".join(hashes) if hashes else "")}
    _INDEX_CSP_CACHE[entry] = (mtime, headers)
    return headers


def _index_response():
    entry = legacy.react_index()
    headers = None
    if os.path.normpath(entry) != os.path.normpath(legacy.WEB_INDEX):
        # The legacy fallback still uses inline scripts and keeps relying
        # on the other headers (see _security_headers).
        headers = _react_csp(entry)
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
                "foap-mark.png": "image/png",
                "favicon.png": "image/png"}


@router.get("/foap-logo.png")
def serve_logo():
    return _brand_file("foap-logo.png")


@router.get("/foap-mark.png")
def serve_mark():
    return _brand_file("foap-mark.png")


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


@router.get("/api/sample-files")
def sample_files(request: Request, conn=Depends(get_product_conn),
                 _emp=Depends(get_current_employee)):
    """Employee-visible sample report/workbook history.

    Read-only view over the persisted sample_files table (never a
    render-time fixture): ordinary employees can list and download;
    mutation stays behind the admin pack endpoints.
    """
    _ = request
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    batch = (st["receipt"]["batch_id"] if st["receipt"] else "")
    rows = conn.execute(
        "SELECT file_key, name, format, mime, bytes, sha256, created_at"
        " FROM sample_files WHERE file_key LIKE ? ORDER BY created_at",
        (batch + "/%",)).fetchall() if batch else []
    return {"pack_key": demo_pack.PACK_KEY_V2, "batch_id": batch,
            "files": [{"key": r[0], "name": r[1], "format": r[2],
                       "mime": r[3], "bytes": r[4], "sha256": r[5],
                       "created_at": r[6],
                       "url": "/api/sample-files/%s" % r[0]}
                      for r in rows]}


@router.get("/api/sample-files/{file_key:path}")
def sample_file_download(file_key: str, request: Request,
                         conn=Depends(get_product_conn),
                         _emp=Depends(get_current_employee)):
    """Download a persisted sample file (viewer permission)."""
    import os as _os

    from ci_backend.actions import _media_dir
    from creative_intel import demo_pack

    _ = request
    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    batch = (st["receipt"]["batch_id"] if st["receipt"] else "")
    if not batch or not file_key.startswith(batch + "/"):
        raise HTTPException(status_code=404,
                            detail={"error": "Sample file not found."})
    row = conn.execute(
        "SELECT name, mime FROM sample_files WHERE file_key=?",
        (file_key,)).fetchone()
    if not row:
        raise HTTPException(status_code=404,
                            detail={"error": "Sample file not found."})
    path = _os.path.join(_media_dir(None), "sample", batch, row[0])
    if not _os.path.isfile(path):
        raise HTTPException(status_code=410, detail={
            "error": "Sample file was deleted from disk. The import"
                     " receipt is kept; files are not regenerated."})
    return FileResponse(path, media_type=row[1], filename=row[0])


# React Router client paths: serve the app shell so deep links and
# refreshes work (item 51). Explicit list — unknown paths still 404.
_SPA_PATHS = ("campaigns", "creatives", "compare", "benchmarks",
              "reports", "profile", "settings", "admin", "analyst",
              "insights", "workbook", "ask", "dashboard", "providers")


@router.get("/{spa_path}")
def spa_fallback(spa_path: str):
    if spa_path not in _SPA_PATHS:
        raise HTTPException(status_code=404, detail={"error": "not found"})
    return _index_response()

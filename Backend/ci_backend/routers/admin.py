"""Admin routes (FastAPI port of the legacy /api/admin/* surface)."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ci_backend import employees as emp
from ci_backend import product_audit as paudit
from ci_backend import security_log
from ci_backend.deps import (
    admin_rate_limit,
    get_current_admin,
    get_db,
    get_product_conn,
    get_settings,
    json_payload,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_MOVES = {
    "approve": ("active", "EMPLOYEE_APPROVED"),
    "suspend": ("suspended", "EMPLOYEE_SUSPENDED"),
    "reactivate": ("active", "EMPLOYEE_REACTIVATED"),
    "revoke": ("revoked", "EMPLOYEE_REVOKED"),
}


def _employee_payload(employee) -> dict:
    return {"employee": emp.public_employee(employee).model_dump()}


class EmployeeCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(default="", max_length=120)
    last_name: str = Field(default="", max_length=120)
    role: str = Field(default="employee", pattern="^(admin|employee)$")


class RoleChange(BaseModel):
    role: str = Field(pattern="^(admin|employee)$")


class EmployeeSearch(BaseModel):
    search: str = Field(default="", max_length=120)
    filter: str = Field(
        default="", pattern="^(|all|pending|active|suspended|revoked"
        "|admin|employee)$")


def _validated(model, body: dict):
    try:
        return model.model_validate(body or {})
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid request: %s" % exc})


@router.get("/employees")
def list_employees(request: Request, db=Depends(get_db),
                   admin=Depends(get_current_admin)):
    params = _validated(EmployeeSearch, {
        "search": request.query_params.get("search", ""),
        "filter": request.query_params.get("filter", "")})
    return {"employees": [e.model_dump() for e in
                          emp.admin_list(db, params.search, params.filter)]}


@router.post("/employees")
async def create_employee(request: Request, db=Depends(get_db),
                          admin=Depends(get_current_admin),
                          _rl=Depends(admin_rate_limit)):
    body = _validated(EmployeeCreate, await json_payload(request))
    try:
        employee = emp.admin_create(
            db, admin.id, body.email,
            body.first_name, body.last_name, body.role)
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)


@router.post("/employees/{employee_id}/sessions/revoke")
def revoke_employee_sessions(employee_id: str, request: Request,
                             db=Depends(get_db),
                             admin=Depends(get_current_admin),
                             _rl=Depends(admin_rate_limit)):
    """Admin: invalidate every session of one employee (audited)."""
    try:
        count = emp.revoke_all_sessions(db, admin.id, unquote(employee_id))
    except emp.StoreError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    security_log.event("session_revocation", actor=admin.id,
                       target=unquote(employee_id),
                       detail="%d session(s) revoked by admin" % count)
    return {"ok": True, "revoked": count}


@router.get("/audit")
def audit(request: Request, db=Depends(get_db),
          admin=Depends(get_current_admin)):
    return {"events": [e.model_dump() for e in emp.admin_audit_list(
        db, request.query_params.get("limit", "100"))]}


@router.get("/ops")
def ops(request: Request, db=Depends(get_db),
        admin=Depends(get_current_admin)):
    """Operations health: storage sizes, disk space, job durations and
    recent sync failures, with plain-language warnings. Admin-only:
    infrastructure detail, never payloads or secrets."""
    _ = (db, admin)
    import os
    import sqlite3

    from ci_backend import actions as legacy
    from ci_backend.observability import ops_summary

    db_path = str(request.app.state.ci_db_path)
    try:
        media_dir = legacy._media_dir()
    except Exception:
        media_dir = ""
    backup_dir = os.environ.get("BACKUP_DIR",
                                "/var/backups/creative-intelligence")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        from creative_intel import schema
        schema.init_db(conn)
        return ops_summary(conn, db_path=db_path, media_dir=media_dir,
                           backup_dir=backup_dir)
    finally:
        conn.close()


@router.post("/demo/seed")
def seed_demo(request: Request, db=Depends(get_db),
              admin=Depends(get_current_admin),
              settings=Depends(get_settings),
              _rl=Depends(admin_rate_limit)):
    """Retired: the legacy refillable demo filler is superseded by the
    one-time presentation pack (Admin -> Advanced -> Demo Data ->
    Add Demo Data Once), which records a persistent receipt and never
    resurrects deleted rows. Returns 410 so old callers fail loudly
    instead of silently repopulating."""
    _ = (request, db, settings, _rl)
    security_log.event("demo_seed_retired", actor=admin.id,
                       target="demo", detail="legacy seed route retired")
    raise HTTPException(status_code=410, detail={
        "error": "The legacy demo seed is retired. Use Admin -> Advanced"
                 " -> Demo Data -> Add Demo Data Once."})


@router.get("/audit/product")
def audit_product(request: Request, db=Depends(get_db),
                  admin=Depends(get_current_admin)):
    """Product audit trail: uploads, analyses, verifications, syncs,
    reports and connector changes. Rows carry request/employee IDs,
    action, target and result only — never payloads or secrets."""
    _ = (db, admin)
    import sqlite3

    limit = request.query_params.get("limit", "100")
    conn = sqlite3.connect(request.app.state.ci_db_path,
                           check_same_thread=False)
    try:
        paudit.ensure(conn)
        return {"events": paudit.recent(conn, limit)}
    finally:
        conn.close()


@router.get("/employees/{employee_id}")
def get_employee(employee_id: str, db=Depends(get_db),
                 admin=Depends(get_current_admin)):
    employee = emp.get_employee(db, unquote(employee_id))
    if employee is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Employee not found."})
    return _employee_payload(employee)


@router.post("/employees/{employee_id}/{verb}")
async def employee_action(employee_id: str, verb: str, request: Request,
                          db=Depends(get_db),
                          admin=Depends(get_current_admin),
                          _rl=Depends(admin_rate_limit)):
    raw = await json_payload(request)
    target = unquote(employee_id)
    try:
        if verb in _MOVES:
            status, action = _MOVES[verb]
            employee = emp.admin_set_status(
                db, admin.id, target, status, action)
            security_log.event("employee_status_change", actor=admin.id,
                               target=target,
                               detail="status=%s" % status)
        elif verb == "role":
            body = _validated(RoleChange, raw)
            employee = emp.admin_set_role(
                db, admin.id, target, body.role)
            security_log.event("role_change", actor=admin.id,
                               target=target,
                               detail="role=%s" % body.role)
        else:
            raise HTTPException(status_code=404,
                                detail={"error": "not found"})
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)


class PackRename(BaseModel):
    kind: str = Field(pattern="^(campaign|creative)$")
    id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)


@router.get("/demo/pack/status")
def pack_status(request: Request, conn=Depends(get_product_conn),
                admin=Depends(get_current_admin)):
    """One-time pack receipt + live remaining counts (audited read)."""
    _ = admin
    from creative_intel import demo_pack

    return demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)


@router.get("/demo/pack/preview")
def pack_preview(request: Request, conn=Depends(get_product_conn),
                 admin=Depends(get_current_admin),
                 settings=Depends(get_settings)):
    """What Add Demo Data Once will create. No writes."""
    _ = admin
    from creative_intel import demo_pack

    out = demo_pack.preview_v2(
        conn, workspace=(settings.environment or "local"))
    out["status"] = demo_pack.pack_status(
        conn, demo_pack.PACK_KEY_V2)["status"]
    out["migration"] = demo_pack.migration_preview(conn)
    return out


@router.post("/demo/pack/import")
def pack_import(request: Request, conn=Depends(get_product_conn),
                admin=Depends(get_current_admin),
                settings=Depends(get_settings),
                _rl=Depends(admin_rate_limit)):
    """Add Demo Data Once (v2: 5 campaigns x 3 creatives).
    Receipt-gated: a completed import retried returns the existing
    receipt without touching data; concurrent callers collapse onto
    the single receipt row. An active v1 pack refuses with a
    migration pointer instead of installing beside it."""
    from creative_intel import demo_pack

    before = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    if before["status"] in ("added", "partially_removed", "removed"):
        security_log.event("demo_pack_import_skip", actor=admin.id,
                           target=demo_pack.PACK_KEY_V2,
                           detail="status=%s" % before["status"])
        out = dict(before)
        out["created"] = False
        return out
    core = demo_pack.import_pack_v2(
        conn, imported_by=admin.id,
        workspace=(settings.environment or "local"))
    if core.get("migration_required") or not core.get("created", True) \
            or core.get("phase") != "core":
        return core
    final = demo_pack.finalize_pack_v2(
        conn, core["batch_id"], imported_by=admin.id,
        core_counts=core["counts"])
    security_log.event("demo_pack_import", actor=admin.id,
                       target=demo_pack.PACK_KEY_V2,
                       detail="batch=%s campaigns=5 creatives=15"
                       % core["batch_id"])
    return final


@router.get("/demo/pack/migration/preview")
def pack_migration_preview(request: Request,
                           conn=Depends(get_product_conn),
                           admin=Depends(get_current_admin)):
    """Explicit v1 -> v2 migration preview. No writes."""
    _ = admin
    from creative_intel import demo_pack

    return demo_pack.migration_preview(conn)


@router.post("/demo/pack/migration/apply")
async def pack_migration_apply(request: Request,
                         conn=Depends(get_product_conn),
                         admin=Depends(get_current_admin),
                         _rl=Depends(admin_rate_limit)):
    """Authorised v1 -> v2 migration. Requires explicit
    {authorize: true}; deletes only live surplus sample-owned
    campaigns and writes the v2 receipt over the same batch."""
    from creative_intel import demo_pack

    raw = await json_payload(request)
    out = demo_pack.migrate_to_v2(conn, imported_by=admin.id,
                                  authorize=bool(raw.get("authorize")))
    if not out.get("authorized"):
        return out
    security_log.event("demo_pack_migrate", actor=admin.id,
                       target=demo_pack.PACK_KEY_V2,
                       detail="deleted=%s" % ",".join(out["deleted"]))
    return out


@router.post("/demo/pack/remove")
async def pack_remove(request: Request, conn=Depends(get_product_conn),
                      admin=Depends(get_current_admin),
                      _rl=Depends(admin_rate_limit)):
    """Remove All Demo Data: batch-scoped only. Requires explicit
    confirmation ({confirm: true}) plus the batch id."""
    from creative_intel import demo_pack

    raw = await json_payload(request)
    if not raw.get("confirm"):
        raise HTTPException(status_code=409, detail={
            "error": "Confirmation required.",
            "preview": demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)["remaining"]})
    receipt = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)["receipt"]
    if receipt is None or raw.get("batch_id") != receipt["batch_id"]:
        raise HTTPException(status_code=409, detail={
            "error": "Batch mismatch: removal is scoped to the"
                     " imported pack only."})
    out = demo_pack.remove_pack(conn, receipt["batch_id"])
    security_log.event("demo_pack_remove", actor=admin.id,
                       target=demo_pack.PACK_KEY_V2,
                       detail="batch=%s" % receipt["batch_id"])
    return out


@router.get("/demo/pack/impact")
def pack_impact(request: Request, conn=Depends(get_product_conn),
                admin=Depends(get_current_admin)):
    """Exact affected-record counts before a campaign delete."""
    _ = admin
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    if st["receipt"] is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Pack never imported."})
    cid = request.query_params.get("campaign_id", "")
    return demo_pack.campaign_impact(conn, st["receipt"]["batch_id"],
                                     cid)


@router.delete("/demo/pack/campaigns/{campaign_id}")
def pack_delete_campaign(campaign_id: str, request: Request,
                         conn=Depends(get_product_conn),
                         admin=Depends(get_current_admin),
                         _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_campaign(conn, st["receipt"]["batch_id"],
                                        campaign_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    security_log.event("demo_pack_delete_campaign", actor=admin.id,
                       target=campaign_id, detail="batch=%s" %
                       st["receipt"]["batch_id"])
    _ = request
    return out


@router.delete("/demo/pack/creatives/{creative_key}")
def pack_delete_creative(creative_key: str, request: Request,
                         conn=Depends(get_product_conn),
                         admin=Depends(get_current_admin),
                         _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_creative(conn, st["receipt"]["batch_id"],
                                        creative_key)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    security_log.event("demo_pack_delete_creative", actor=admin.id,
                       target=creative_key, detail="batch=%s" %
                       st["receipt"]["batch_id"])
    _ = request
    return out


@router.post("/demo/pack/rename")
async def pack_rename(request: Request, conn=Depends(get_product_conn),
                      admin=Depends(get_current_admin),
                      _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    body = _validated(PackRename, await json_payload(request))
    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        if body.kind == "campaign":
            out = demo_pack.rename_campaign(conn,
                                            st["receipt"]["batch_id"],
                                            body.id, body.name)
        else:
            out = demo_pack.rename_creative(conn,
                                            st["receipt"]["batch_id"],
                                            body.id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    security_log.event("demo_pack_rename", actor=admin.id,
                       target=body.id, detail="kind=%s" % body.kind)
    return out


@router.delete("/demo/pack/conversations/{conversation_id}")
def pack_delete_conversation(conversation_id: str, request: Request,
                             conn=Depends(get_product_conn),
                             admin=Depends(get_current_admin),
                             _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_conversation(
            conn, st["receipt"]["batch_id"], conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    security_log.event("demo_pack_delete_conversation", actor=admin.id,
                       target=conversation_id, detail="batch=%s" %
                       st["receipt"]["batch_id"])
    _ = request
    return out


@router.delete("/demo/pack/findings/{finding_id}")
def pack_delete_finding(finding_id: str, request: Request,
                        conn=Depends(get_product_conn),
                        admin=Depends(get_current_admin),
                        _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_finding(conn, st["receipt"]["batch_id"],
                                       finding_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    _ = request
    return out


@router.delete("/demo/pack/views/{view_id}")
def pack_delete_view(view_id: int, request: Request,
                     conn=Depends(get_product_conn),
                     admin=Depends(get_current_admin),
                     _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_sample_view(conn,
                                           st["receipt"]["batch_id"],
                                           view_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    _ = request
    return out


@router.get("/demo/pack/files")
def pack_files(request: Request, conn=Depends(get_product_conn),
               admin=Depends(get_current_admin)):
    _ = (request, admin)
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    if st["receipt"] is None:
        return {"files": []}
    rows = conn.execute(
        "SELECT file_key, name, format, mime, bytes, created_at"
        " FROM sample_files WHERE batch_id=? ORDER BY name",
        (st["receipt"]["batch_id"],)).fetchall()
    return {"files": [
        {"file_key": r[0], "name": r[1], "format": r[2], "mime": r[3],
         "bytes": r[4], "created_at": r[5]} for r in rows]}


@router.get("/demo/pack/files/{file_key:path}")
def pack_file_download(file_key: str, request: Request,
                       conn=Depends(get_product_conn),
                       admin=Depends(get_current_admin)):
    import os as _os

    from fastapi.responses import FileResponse

    from ci_backend.actions import _media_dir

    _ = admin
    row = conn.execute(
        "SELECT name, mime FROM sample_files WHERE file_key=?",
        (file_key,)).fetchone()
    if not row:
        raise HTTPException(status_code=404,
                            detail={"error": "Sample file not found."})
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    batch = (file_key.split("/")[0] if "/" in file_key else "")
    if st["receipt"] is None or batch != st["receipt"]["batch_id"]:
        raise HTTPException(status_code=404,
                            detail={"error": "Sample file not found."})
    path = _os.path.join(_media_dir(None), "sample", batch, row[0])
    if not _os.path.isfile(path):
        raise HTTPException(status_code=410, detail={
            "error": "Sample file was deleted from disk. The import"
                     " receipt is kept; files are not regenerated."})
    _ = request
    return FileResponse(path, media_type=row[1], filename=row[0])


@router.delete("/demo/pack/files/{file_key:path}")
def pack_delete_file(file_key: str, request: Request,
                     conn=Depends(get_product_conn),
                     admin=Depends(get_current_admin),
                     _rl=Depends(admin_rate_limit)):
    from creative_intel import demo_pack

    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    try:
        out = demo_pack.delete_sample_file(
            conn, st["receipt"]["batch_id"], file_key)
    except ValueError as exc:
        raise HTTPException(status_code=404,
                            detail={"error": str(exc)})
    _ = request
    return out

"""Admin provider management (single-active-provider backend).

Every route requires get_current_admin; mutations additionally take
admin_rate_limit. Audit goes through security_log with WHO did WHAT
to WHICH provider — never secret values. No response in this module
carries secret material (only has_secret/configured booleans).

Conventions (routers/admin.py pattern): request bodies parse through
json_payload + _validated -> 409 on schema errors. ValueError from
bad input (unknown id, unsupported entry, unsafe base) -> 409;
ProviderUnavailable from live transport/validation -> 502; stale
singleton revision on activate/deactivate -> 409 with the current
revision returned.
"""

from __future__ import annotations

from datetime import datetime, timezone

from creative_intel import dispatcher as dispatcher_mod
from creative_intel import provider_inventory as inv
from creative_intel import providers as providers_mod
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from ci_backend import security_log
from ci_backend.db import (
    ActiveProviderSelection,
    ProviderConfig,
    ProviderModelCache,
)
from ci_backend.deps import (
    admin_rate_limit,
    get_current_admin,
    get_db,
    json_payload,
)

router = APIRouter(prefix="/api/admin/providers", tags=["admin-providers"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validated(model, body: dict):
    try:
        return model.model_validate(body or {})
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid request: %s" % exc})


class PutBody(BaseModel):
    base_url: str | None = None
    secret: str | None = None
    confirm: bool = False


class ActivateBody(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=0)


class DeactivateBody(BaseModel):
    revision: int = Field(ge=0)


def _spec_or_404(provider_id: str) -> dict:
    spec = inv.BY_ID.get(provider_id)
    if spec is None:
        raise HTTPException(status_code=404,
                            detail={"error": "unknown provider %r"
                                    % (provider_id,)})
    return spec


def _require_supported(spec: dict) -> None:
    if not spec.get("supported"):
        raise HTTPException(
            status_code=409,
            detail={"error": "%s is listed but unsupported: %s"
                    % (spec["id"], spec.get("unsupported_reason", ""))})


def _video_info(provider_id: str, model_id: str) -> dict:
    """Video-workflow support flags for one exact model id.

    video_eligible is True only for ids verified native-video capable
    in official vendor docs (item 32). frame_eligible is True for the
    ffmpeg breakdown (timed JPEG frames + WAV): image-level models
    qualify because frames are plain images. Additive: older clients
    ignore the keys.
    """
    level, doc = inv.frame_support(provider_id, model_id)
    return {"support": level, "video_eligible": level == "native-video",
            "frame_eligible": inv.frame_eligible(provider_id, model_id),
            "support_doc": doc or None}


def _cache_stats(db, provider_id: str) -> dict:
    rows = db.execute(select(ProviderModelCache).where(
        ProviderModelCache.provider_id == provider_id)).scalars().all()
    offered = [r for r in rows if r.offered]
    fetched = max([r.fetched_at for r in rows if r.fetched_at]
                  or [""])
    fresh = any(dispatcher_mod._fresh_enough(r.fetched_at) for r in offered)
    return {"models_cached": len(rows), "offered_count": len(offered),
            "fetched_at": fetched or None, "stale": not fresh,
            "cached_models": [{"id": r.model_id,
                               "label": r.display or r.model_id,
                               **_video_info(provider_id, r.model_id)}
                              for r in offered]}


def _provider_view(db, cfg: ProviderConfig) -> dict:
    spec = inv.BY_ID.get(cfg.provider_id) or {}
    stats = _cache_stats(db, cfg.provider_id)
    has_secret = bool(cfg.secret_enc)
    return {"provider_id": cfg.provider_id, "display": cfg.display,
            "kind": cfg.kind, "supported": bool(spec.get("supported", True)),
            "unsupported_reason": spec.get("unsupported_reason"),
            "base_url": cfg.base_url, "has_secret": has_secret,
            "secret_updated_at": cfg.secret_updated_at,
            "configured": has_secret or cfg.provider_id == "ollama",
            **stats}


def _selection_view(db) -> tuple:
    # Sessions run with expire_on_commit=False and several writers
    # use Core UPDATE/DELETE (bypassing the identity map), so expire
    # before reading: otherwise a just-deactivated selection still
    # looks active in this request's response.
    db.expire_all()
    sel = db.get(ActiveProviderSelection, 1)
    if sel is None:
        return None, 0
    if not sel.provider_id or not sel.model_id:
        return None, sel.revision
    # Surface video eligibility on the active selection itself so an
    # unsupported-but-active model is visible instead of failing
    # opaquely later (no silent fallback anywhere in this path).
    return {"provider_id": sel.provider_id, "model_id": sel.model_id,
            "revision": sel.revision, "updated_by": sel.updated_by,
            "updated_at": sel.updated_at,
            **_video_info(sel.provider_id, sel.model_id)}, sel.revision


def _store_cache(db, provider_id: str, offered: list, fetched_at: str) -> None:
    db.execute(delete(ProviderModelCache).where(
        ProviderModelCache.provider_id == provider_id))
    for item in offered:
        db.add(ProviderModelCache(provider_id=provider_id,
                                 model_id=item["id"],
                                 display=item.get("label", item["id"]),
                                 offered=1, fetched_at=fetched_at))


def _decrypt_or_502(cfg: ProviderConfig) -> str | None:
    if not cfg.secret_enc:
        return None
    from ci_backend import token_crypto
    try:
        return token_crypto.decrypt_secret(cfg.secret_enc)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": "stored secret for %s is undecryptable "
                    "(master key mismatch): re-save it, then retry"
                    % cfg.provider_id}) from exc


@router.get("")
@router.get("/")
def list_providers(request: Request, db=Depends(get_db),
                   admin=Depends(get_current_admin)):
    _ = (request, admin)
    cfgs = db.execute(select(ProviderConfig).order_by(
        ProviderConfig.provider_id)).scalars().all()
    active, revision = _selection_view(db)
    return {"providers": [_provider_view(db, c) for c in cfgs],
            "active": active, "current_revision": revision}


@router.post("/activate")
async def activate(request: Request, db=Depends(get_db),
                   admin=Depends(get_current_admin),
                   _rl=Depends(admin_rate_limit)):
    body = _validated(ActivateBody, await json_payload(request))
    spec = _spec_or_404(body.provider_id)
    _require_supported(spec)
    sel = db.get(ActiveProviderSelection, 1)
    current = sel.revision if sel is not None else 0
    if body.revision != current:
        raise HTTPException(status_code=409, detail={
            "error": "selection changed since revision %d" % body.revision,
            "current_revision": current})
    cfg = db.get(ProviderConfig, body.provider_id)
    secret_stored = bool(cfg is not None and cfg.secret_enc)
    if body.provider_id != "ollama" and body.provider_id != "litellm" \
            and not secret_stored:
        raise HTTPException(status_code=409, detail={
            "error": "no secret stored for %s: save one, test it, refresh"
                     " the catalog, then activate" % body.provider_id,
            "current_revision": current})
    if body.provider_id == "litellm" and not secret_stored \
            and not (cfg is not None and cfg.base_url):
        raise HTTPException(status_code=409, detail={
            "error": "litellm needs a base_url (or a secret): save one,"
                     " refresh the catalog, then activate",
            "current_revision": current})
    rows = db.execute(select(ProviderModelCache).where(
        ProviderModelCache.provider_id == body.provider_id,
        ProviderModelCache.model_id == body.model_id,
        ProviderModelCache.offered == 1)).scalars().all()
    # Exact-model-only: the row match above is byte-for-byte, never
    # fuzzy — a renamed/removed vendor id must fail loudly.
    if not rows:
        raise HTTPException(status_code=409, detail={
            "error": "model %r is not in the offered catalog for %s:"
                     " refresh the catalog and pick an offered model"
                     % (body.model_id, body.provider_id),
            "current_revision": current})
    if not any(dispatcher_mod._fresh_enough(r.fetched_at) for r in rows):
        raise HTTPException(status_code=409, detail={
            "error": "model catalog for %s is stale (older than 24h):"
                     " refresh it before activating" % body.provider_id,
            "current_revision": current})
    now = _now_iso()
    if sel is None:
        db.add(ActiveProviderSelection(
            id=1, provider_id=body.provider_id, model_id=body.model_id,
            revision=current + 1, updated_by=admin.id, updated_at=now))
    else:
        hit = db.execute(
            ActiveProviderSelection.__table__.update().where(
                ActiveProviderSelection.id == 1,
                ActiveProviderSelection.revision == current).values(
                    provider_id=body.provider_id, model_id=body.model_id,
                    revision=current + 1, updated_by=admin.id,
                    updated_at=now)).rowcount
        if not hit:
            sel = db.get(ActiveProviderSelection, 1)
            raise HTTPException(status_code=409, detail={
                "error": "selection changed concurrently",
                "current_revision": sel.revision if sel else 0})
    db.commit()
    security_log.event("provider_activated", actor=admin.id,
                       target=body.provider_id,
                       detail="model=%s revision=%d"
                       % (body.model_id, current + 1))
    active, revision = _selection_view(db)
    return {"ok": True, "active": active, "current_revision": revision}


@router.post("/deactivate")
async def deactivate(request: Request, db=Depends(get_db),
                     admin=Depends(get_current_admin),
                     _rl=Depends(admin_rate_limit)):
    body = _validated(DeactivateBody, await json_payload(request))
    sel = db.get(ActiveProviderSelection, 1)
    current = sel.revision if sel is not None else 0
    if body.revision != current:
        raise HTTPException(status_code=409, detail={
            "error": "selection changed since revision %d" % body.revision,
            "current_revision": current})
    if sel is None:
        return {"ok": True, "active": None, "current_revision": 0}
    now = _now_iso()
    hit = db.execute(
        ActiveProviderSelection.__table__.update().where(
            ActiveProviderSelection.id == 1,
            ActiveProviderSelection.revision == current).values(
                provider_id=None, model_id=None, revision=current + 1,
                updated_by=admin.id, updated_at=now)).rowcount
    if not hit:
        sel = db.get(ActiveProviderSelection, 1)
        raise HTTPException(status_code=409, detail={
            "error": "selection changed concurrently",
            "current_revision": sel.revision if sel else 0})
    db.commit()
    security_log.event("provider_deactivated", actor=admin.id,
                       target=sel.provider_id or "",
                       detail="revision=%d" % (current + 1))
    return {"ok": True, "active": None, "current_revision": current + 1}


@router.put("/{provider_id}")
async def put_config(provider_id: str, request: Request, db=Depends(get_db),
                     admin=Depends(get_current_admin),
                     _rl=Depends(admin_rate_limit)):
    from urllib.parse import unquote

    from ci_backend import token_crypto

    provider_id = unquote(provider_id)
    spec = _spec_or_404(provider_id)
    _require_supported(spec)
    body = _validated(PutBody, await json_payload(request))
    fields = body.model_fields_set
    cfg = db.get(ProviderConfig, provider_id)
    if cfg is None:
        cfg = ProviderConfig(provider_id=provider_id,
                             display=spec.get("display", provider_id),
                             kind=spec.get("kind", "api_key"))
        db.add(cfg)
    sel = db.get(ActiveProviderSelection, 1)
    is_active = bool(sel is not None and sel.provider_id == provider_id
                     and sel.model_id)

    new_base = cfg.base_url
    if "base_url" in fields:
        raw = (body.base_url or "").strip()
        if not raw:
            new_base = None
        else:
            try:
                new_base = inv.assert_safe_base_url(raw)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={
                    "error": "unsafe base_url: %s" % exc})

    secret_op = "keep"
    new_secret = None
    if "secret" in fields:
        if body.secret is None or not body.secret.strip():
            secret_op = "remove"
        else:
            if len(body.secret) > 4096:
                raise HTTPException(status_code=409, detail={
                    "error": "secret too long (max 4096 characters)"})
            secret_op = "replace"
            new_secret = body.secret.strip()

    if secret_op == "remove" and is_active and not body.confirm:
        raise HTTPException(status_code=409, detail={
            "error": "provider %s is ACTIVE: resend with"
                     " {\"confirm\": true} to clear its secret and"
                     " atomically deactivate" % provider_id,
            "confirm_required": True,
            "current_revision": sel.revision})

    now = _now_iso()
    if secret_op == "remove":
        cfg.secret_enc = None
        cfg.secret_updated_at = None
        cfg.base_url = new_base
        cfg.updated_at = now
        db.execute(delete(ProviderModelCache).where(
            ProviderModelCache.provider_id == provider_id))
        revision = sel.revision if sel else 0
        if is_active:
            # Confirm path: clearing the active secret atomically
            # pauses inference in the same commit.
            revision = sel.revision + 1
            db.execute(
                ActiveProviderSelection.__table__.update().where(
                    ActiveProviderSelection.id == 1,
                    ActiveProviderSelection.revision == sel.revision
                ).values(provider_id=None, model_id=None,
                         revision=revision, updated_by=admin.id,
                         updated_at=now))
            security_log.event("provider_secret_removed", actor=admin.id,
                               target=provider_id,
                               detail="active secret cleared; deactivated"
                                      " revision=%d" % revision)
        else:
            security_log.event("provider_secret_removed", actor=admin.id,
                               target=provider_id, detail="secret cleared")
        db.commit()
        active, current = _selection_view(db)
        return {"ok": True, "provider_id": provider_id,
                "configured": False, "has_secret": False,
                "offered_count": 0, "active": active,
                "current_revision": current}

    if secret_op == "replace" or new_base != cfg.base_url:
        # Any credential/endpoint change on the ACTIVE config is
        # validate-then-swap: the new values are proven against live
        # discovery BEFORE the stored row changes, so a failed
        # validation keeps the old secret (and old base) serving.
        check_secret = (new_secret if secret_op == "replace"
                        else _decrypt_or_502(cfg))
        if is_active:
            try:
                offered, _latency = dispatcher_mod.probe_provider(
                    provider_id, check_secret, new_base)
            except ValueError as exc:
                raise HTTPException(status_code=409,
                                    detail={"error": str(exc)})
            except providers_mod.ProviderUnavailable as exc:
                raise HTTPException(status_code=502,
                                    detail={"error": str(exc)})
            if secret_op == "replace":
                cfg.secret_enc = token_crypto.encrypt_secret(new_secret)
                cfg.secret_updated_at = now
            cfg.base_url = new_base
            cfg.updated_at = now
            _store_cache(db, provider_id, offered, now)
            db.commit()
            security_log.event("provider_config_saved", actor=admin.id,
                               target=provider_id,
                               detail="active config validated+swapped")
        else:
            if secret_op == "replace":
                cfg.secret_enc = token_crypto.encrypt_secret(new_secret)
                cfg.secret_updated_at = now
            cfg.base_url = new_base
            cfg.updated_at = now
            db.execute(delete(ProviderModelCache).where(
                ProviderModelCache.provider_id == provider_id))
            db.commit()
            security_log.event("provider_config_saved", actor=admin.id,
                               target=provider_id,
                               detail="stored; cache cleared pending refresh")
        db.refresh(cfg)
        stats = _cache_stats(db, provider_id)
        active, current = _selection_view(db)
        return {"ok": True, "provider_id": provider_id,
                "configured": bool(cfg.secret_enc)
                or provider_id == "ollama",
                "has_secret": bool(cfg.secret_enc),
                "offered_count": stats["offered_count"],
                "active": active, "current_revision": current}

    # Base/secret untouched (e.g. confirm-only or empty PUT).
    db.commit()
    stats = _cache_stats(db, provider_id)
    active, current = _selection_view(db)
    return {"ok": True, "provider_id": provider_id,
            "configured": bool(cfg.secret_enc)
            or provider_id == "ollama",
            "has_secret": bool(cfg.secret_enc),
            "offered_count": stats["offered_count"],
            "active": active, "current_revision": current}


@router.post("/{provider_id}/test")
async def test_config(provider_id: str, request: Request, db=Depends(get_db),
                      admin=Depends(get_current_admin),
                      _rl=Depends(admin_rate_limit)):
    from urllib.parse import unquote

    provider_id = unquote(provider_id)
    spec = _spec_or_404(provider_id)
    _require_supported(spec)
    cfg = db.get(ProviderConfig, provider_id)
    secret = _decrypt_or_502(cfg) if cfg is not None else None
    if not (secret or "") and provider_id not in ("ollama", "litellm"):
        raise HTTPException(status_code=409, detail={
            "error": "no secret stored for %s: save one first"
                     % provider_id})
    base = (cfg.base_url if cfg is not None else None) or None
    try:
        offered, latency_ms = dispatcher_mod.probe_provider(
            provider_id, secret, base)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    except providers_mod.ProviderUnavailable as exc:
        security_log.event("provider_test_failed", actor=admin.id,
                           target=provider_id, detail="validation failed")
        raise HTTPException(status_code=502,
                            detail={"error": str(exc),
                                    "offered_count": 0})
    security_log.event("provider_tested", actor=admin.id,
                       target=provider_id,
                       detail="offered=%d latency_ms=%d"
                       % (len(offered), latency_ms))
    return {"ok": True, "provider_id": provider_id,
            "latency_ms": latency_ms, "offered_count": len(offered),
            "offered": offered[:200]}


@router.post("/{provider_id}/refresh")
async def refresh_catalog(provider_id: str, request: Request,
                          db=Depends(get_db),
                          admin=Depends(get_current_admin),
                          _rl=Depends(admin_rate_limit)):
    from urllib.parse import unquote

    provider_id = unquote(provider_id)
    spec = _spec_or_404(provider_id)
    _require_supported(spec)
    cfg = db.get(ProviderConfig, provider_id)
    secret = _decrypt_or_502(cfg) if cfg is not None else None
    if not (secret or "") and provider_id not in ("ollama", "litellm"):
        raise HTTPException(status_code=409, detail={
            "error": "no secret stored for %s: save one first"
                     % provider_id})
    base = (cfg.base_url if cfg is not None else None) or None
    try:
        offered, _latency = dispatcher_mod.probe_provider(
            provider_id, secret, base)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    except providers_mod.ProviderUnavailable as exc:
        # Preserve the last catalog: rows (and their fetched_at) are
        # untouched; the response marks stale and offers the retry.
        stats = _cache_stats(db, provider_id)
        security_log.event("provider_refresh_failed", actor=admin.id,
                           target=provider_id, detail="kept last catalog")
        raise HTTPException(status_code=502, detail={
            "error": str(exc), "stale": True,
            "fetched_at": stats["fetched_at"],
            "offered_count": stats["offered_count"],
            "retry": "POST /api/admin/providers/%s/refresh" % provider_id})
    now = _now_iso()
    _store_cache(db, provider_id, offered, now)
    db.commit()
    security_log.event("provider_refreshed", actor=admin.id,
                       target=provider_id,
                       detail="offered=%d" % len(offered))
    return {"ok": True, "provider_id": provider_id,
            "offered_count": len(offered), "fetched_at": now,
            "stale": False}


@router.post("/{provider_id}/adopt")
async def adopt_secret(provider_id: str, request: Request, db=Depends(get_db),
                       admin=Depends(get_current_admin),
                       _rl=Depends(admin_rate_limit)):
    from urllib.parse import unquote

    from ci_backend import token_crypto

    provider_id = unquote(provider_id)
    spec = _spec_or_404(provider_id)
    _require_supported(spec)
    sources = inv.ADOPT_SOURCES.get(provider_id)
    if not sources:
        raise HTTPException(status_code=409, detail={
            "error": "nothing to adopt for %s (keyless local or"
                     " unsupported entry)" % provider_id})
    cfg = db.get(ProviderConfig, provider_id)
    if cfg is not None and cfg.secret_enc:
        raise HTTPException(status_code=409, detail={
            "error": "a secret is already stored for %s: adoption is"
                     " one-time; use PUT to replace it" % provider_id})
    # Explicit one-time copy from the legacy env/Keychain source into
    # encrypted storage. The value is never logged, never returned,
    # and nothing is activated by this route.
    found = None
    for service in sources:
        value = providers_mod.live_secret(service)
        if value:
            found = value
            break
    if not found:
        env_names = [providers_mod._env_key_name(s) for s in sources]
        raise HTTPException(status_code=409, detail={
            "error": "no legacy secret found for %s" % provider_id,
            "tried_env": env_names, "tried_keychain": list(sources)})
    if cfg is None:
        cfg = ProviderConfig(provider_id=provider_id,
                             display=spec.get("display", provider_id),
                             kind=spec.get("kind", "api_key"))
        db.add(cfg)
    now = _now_iso()
    cfg.secret_enc = token_crypto.encrypt_secret(found)
    cfg.secret_updated_at = now
    cfg.updated_at = now
    db.execute(delete(ProviderModelCache).where(
        ProviderModelCache.provider_id == provider_id))
    db.commit()
    found = None
    security_log.event("provider_adopted", actor=admin.id,
                       target=provider_id,
                       detail="legacy secret adopted; not activated")
    return {"ok": True, "provider_id": provider_id, "has_secret": True,
            "configured": True, "activated": False}

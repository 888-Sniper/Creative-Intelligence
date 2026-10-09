"""Authenticator-app two-factor (RFC 6238) for employee sign-in.

The browser only ever sees a setup secret before it is confirmed, the
one-time recovery codes, and a short-lived challenge cookie. The
secret and the recovery hashes stay encrypted or hashed in the
database. A code never opens a session until it matches.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import secrets
import struct
import time
import urllib.parse

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ci_backend import employees as emp
from ci_backend import token_crypto
from ci_backend.db import EmployeeTotp, TotpChallenge

ISSUER = "Foap"
CHALLENGE_COOKIE = "ci_2fa"
STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1
CHALLENGE_TTL_S = 300
MAX_ATTEMPTS = 5
RECOVERY_COUNT = 8
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class TotpError(Exception):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(token: str) -> str:
    try:
        return hashlib.sha256(token.encode("ascii")).hexdigest()
    except (UnicodeEncodeError, AttributeError):
        return ""


def _b32(raw: bytes) -> str:
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_b32(secret: str) -> bytes:
    text = (secret or "").strip().upper().replace(" ", "")
    pad = "=" * ((8 - len(text) % 8) % 8)
    try:
        return base64.b32decode(text + pad, casefold=True)
    except Exception as exc:
        raise TotpError("That authenticator key is not valid.") from exc


def _hotp(secret: bytes, counter: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return "%0*d" % (DIGITS, code % (10 ** DIGITS))


def matching_step(secret_b32: str, code: str, now: float | None = None) -> int | None:
    """Return the matched time step, or None.

    Prefers the current step, then one step either side, so a slow
    clock still works and a reused older step can be rejected.
    """
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) != DIGITS or digits != (code or "").strip():
        return None
    try:
        key = _decode_b32(secret_b32)
    except TotpError:
        return None
    moment = time.time() if now is None else now
    current = int(moment) // STEP_SECONDS
    for step in (current, current - 1, current + 1):
        if step < 0:
            continue
        if hmac.compare_digest(_hotp(key, step), digits):
            return step
    return None


def _row(db: Session, employee_id: str) -> EmployeeTotp | None:
    return db.get(EmployeeTotp, employee_id)


def is_enabled(db: Session, employee_id: str) -> bool:
    row = _row(db, employee_id)
    return bool(row is not None and int(row.enabled or 0) == 1 and row.secret_enc)


def _plain_secret(row: EmployeeTotp, settings=None) -> str:
    try:
        return token_crypto.decrypt_secret(row.secret_enc, settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(
            "Cannot read the authenticator secret. Fix "
            "CREATIVE_INTEL_MASTER_KEY, then set it up again.") from exc


def status(db: Session, employee_id: str) -> dict:
    return {"enabled": is_enabled(db, employee_id)}


def begin_setup(db: Session, employee: emp.Employee, settings=None) -> dict:
    """Store a pending secret and return it once for the authenticator."""
    if is_enabled(db, employee.id):
        raise emp.StoreError("Two-factor authentication is already on.")
    secret = _b32(secrets.token_bytes(20))
    try:
        enc = token_crypto.encrypt_secret(secret, settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(str(exc)) from exc
    row = _row(db, employee.id)
    if row is None:
        row = EmployeeTotp(employee_id=employee.id)
        db.add(row)
    row.secret_enc = enc
    row.enabled = 0
    row.recovery_hashes = ""
    row.last_step = 0
    row.updated_at = emp.utcnow()
    db.commit()
    label = urllib.parse.quote("%s:%s" % (ISSUER, employee.email or employee.id))
    query = urllib.parse.urlencode({
        "secret": secret, "issuer": ISSUER, "digits": str(DIGITS),
        "period": str(STEP_SECONDS),
    })
    return {"secret": secret,
            "otpauth_uri": "otpauth://totp/%s?%s" % (label, query)}


def _recovery_codes() -> list[str]:
    codes = []
    while len(codes) < RECOVERY_COUNT:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        code = "%s-%s" % (raw[:4], raw[4:])
        if code not in codes:
            codes.append(code)
    return codes


def _recovery_hash(code: str) -> str:
    norm = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _hashes(row: EmployeeTotp) -> list[str]:
    try:
        parsed = json.loads(row.recovery_hashes or "[]")
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _consume_recovery(row: EmployeeTotp, code: str) -> bool:
    digest = _recovery_hash(code)
    kept = _hashes(row)
    if not any(hmac.compare_digest(digest, item) for item in kept):
        return False
    row.recovery_hashes = json.dumps(
        [item for item in kept if not hmac.compare_digest(digest, item)])
    return True


def _accept_code(row: EmployeeTotp, code: str, settings=None) -> bool:
    """True when the code is a fresh authenticator step or a recovery code."""
    secret = _plain_secret(row, settings)
    step = matching_step(secret, code)
    if step is not None:
        if int(row.last_step or 0) >= step and int(row.last_step or 0) != 0:
            return False
        row.last_step = step
        return True
    return _consume_recovery(row, code)


def confirm_setup(db: Session, employee: emp.Employee, code: str,
                  settings=None) -> dict:
    row = _row(db, employee.id)
    if row is None or int(row.enabled or 0) == 1 or not row.secret_enc:
        raise emp.StoreError("Set up two-factor authentication first.")
    if not (code or "").strip():
        raise emp.StoreError("Enter the code from your authenticator app.")
    if not _accept_code(row, code, settings):
        db.rollback()
        raise emp.StoreError("That code is not valid.")
    codes = _recovery_codes()
    row.enabled = 1
    row.recovery_hashes = json.dumps([_recovery_hash(item) for item in codes])
    row.updated_at = emp.utcnow()
    db.commit()
    emp._audit(db, employee.id, employee.id, "TWO_FACTOR_ENABLED",
               "off", "on")
    return {"enabled": True, "recovery_codes": codes}


def cancel_setup(db: Session, employee_id: str) -> dict:
    row = _row(db, employee_id)
    if row is not None and int(row.enabled or 0) != 1:
        db.delete(row)
        db.commit()
    return {"enabled": is_enabled(db, employee_id)}


def disable(db: Session, employee: emp.Employee, code: str,
            settings=None) -> dict:
    row = _row(db, employee.id)
    if not is_enabled(db, employee.id) or row is None:
        raise emp.StoreError("Two-factor authentication is off.")
    if not (code or "").strip():
        raise emp.StoreError("Enter the code from your authenticator app.")
    if not _accept_code(row, code, settings):
        db.rollback()
        raise emp.StoreError("That code is not valid.")
    db.delete(row)
    db.commit()
    clear_challenges(db, employee.id)
    emp._audit(db, employee.id, employee.id, "TWO_FACTOR_DISABLED",
               "on", "off")
    return {"enabled": False}


def clear_challenges(db: Session, employee_id: str) -> None:
    db.execute(delete(TotpChallenge).where(
        TotpChallenge.employee_id == employee_id))
    db.commit()


def _sweep(db: Session) -> None:
    cutoff = (_now() - datetime.timedelta(seconds=CHALLENGE_TTL_S)).isoformat()
    db.execute(delete(TotpChallenge).where(TotpChallenge.expires_at < cutoff))
    db.commit()


def issue_challenge(db: Session, employee_id: str) -> str:
    """One live challenge cookie value. Older challenges for this employee die."""
    _sweep(db)
    clear_challenges(db, employee_id)
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(TotpChallenge(
        token_hash=_hash(token), employee_id=employee_id, attempts=0,
        created_at=now.isoformat(timespec="seconds"),
        expires_at=(now + datetime.timedelta(seconds=CHALLENGE_TTL_S)
                    ).isoformat(timespec="seconds")))
    db.commit()
    return token


def _challenge(db: Session, token: str) -> TotpChallenge | None:
    if not token:
        return None
    return db.get(TotpChallenge, _hash(token))


def _challenge_expired(row: TotpChallenge) -> bool:
    try:
        born = datetime.datetime.fromisoformat(row.expires_at)
        if born.tzinfo is None:
            born = born.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return True
    return _now() > born


def take_challenge(db: Session, token: str, code: str,
                   settings=None) -> emp.Employee:
    """Burn a valid challenge into the employee it belongs to.

    A wrong code spends an attempt. The fifth wrong code, an expired
    cookie, or a disabled authenticator drops the challenge.
    """
    _sweep(db)
    row = _challenge(db, token)
    if row is None or _challenge_expired(row):
        if row is not None:
            db.delete(row)
            db.commit()
        raise emp.StoreError("That sign-in expired. Sign in again.")
    employee = emp.get_employee(db, row.employee_id)
    totp = _row(db, row.employee_id) if employee is not None else None
    if employee is None or totp is None or int(totp.enabled or 0) != 1:
        db.delete(row)
        db.commit()
        raise emp.StoreError("That sign-in expired. Sign in again.")
    if not (code or "").strip() or not _accept_code(totp, code, settings):
        row.attempts = int(row.attempts or 0) + 1
        if row.attempts >= MAX_ATTEMPTS:
            db.delete(row)
        db.commit()
        raise emp.StoreError("That code is not valid.")
    db.delete(row)
    db.commit()
    return employee

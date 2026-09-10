"""Security-event logging without secrets.

Uses stdlib logging so uvicorn/systemd/journald capture applies.
Only identities (employee ids, emails), actions and gates are logged.
NEVER pass tokens, API keys, OAuth codes, passwords or magic codes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("creative_intel.security")


def event(action: str, actor: str = "", target: str = "",
          detail: str = "") -> None:
    """Log one security-relevant event. All fields are plain text."""
    parts = ["action=%s" % action]
    if actor:
        parts.append("actor=%s" % actor)
    if target:
        parts.append("target=%s" % target)
    if detail:
        parts.append("detail=%s" % detail)
    logger.info(" ".join(parts))

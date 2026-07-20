"""Shared Sentry bootstrap for bot / worker / admin."""

from __future__ import annotations

import logging
import re
from typing import Any

import sentry_sdk

from app.config import settings

logger = logging.getLogger(__name__)

# Drop lead bodies / chat snippets that may land in exception messages.
_LEAD_KEYS = frozenset({
    "text", "message", "message_text", "message_text_masked",
    "body", "content", "lead_text", "raw_response",
})
_LONG_CYRILLIC = re.compile(r"[\u0400-\u04FF]{40,}")


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > 200 and (_LONG_CYRILLIC.search(value) or "http" in value.lower()):
            return "[redacted]"
        return value
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if str(k).lower() in _LEAD_KEYS else _scrub_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def before_send(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Strip likely lead/PII payloads before upload."""
    for section in ("extra", "contexts", "tags"):
        if section in event and isinstance(event[section], dict):
            event[section] = _scrub_value(event[section])
    if "request" in event and isinstance(event["request"], dict):
        event["request"] = _scrub_value(event["request"])
    exc = event.get("exception") or {}
    for values in exc.get("values") or []:
        if isinstance(values, dict) and isinstance(values.get("value"), str):
            if len(values["value"]) > 300:
                values["value"] = values["value"][:120] + "…[redacted]"
    return event


def init_sentry(service: str) -> bool:
    """Initialize Sentry once per process. Returns True if enabled."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        environment="production",
        release=None,
        send_default_pii=False,
        before_send=before_send,
    )
    sentry_sdk.set_tag("service", service)
    logger.info("Sentry initialized for %s", service)
    return True

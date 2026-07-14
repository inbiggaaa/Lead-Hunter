"""Privacy-safe product analytics for the bot user flow (U2).

Stores counters and minimal event envelopes in Redis. Lead/user message text is
never accepted. Acquisition source and conversion trigger are separate fields.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.cache import get_redis

logger = logging.getLogger(__name__)
EVENT_TTL = 180 * 86400
ALLOWED_CONTEXT = {"category_id", "service_count", "country_id", "city_count", "mode", "trigger", "target_plan", "period", "method", "success", "lead_id", "latency_bucket"}


async def record_event(name: str, user=None, *, user_id: int | None = None,
                       language: str | None = None, plan: str | None = None,
                       acquisition_source: str | None = None,
                       campaign: str | None = None, trigger: str | None = None,
                       context: dict[str, Any] | None = None) -> None:
    """Record a minimal event; failures never break the product flow."""
    uid = user_id or getattr(user, "id", None)
    if not uid:
        return
    lang = language or getattr(user, "language", None) or "ru"
    current_plan = plan or getattr(user, "plan", None) or "free"
    source = acquisition_source or getattr(user, "source", None) or "direct"
    safe = {k: v for k, v in (context or {}).items() if k in ALLOWED_CONTEXT and isinstance(v, (str, int, float, bool, type(None)))}
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    envelope = {"event": name, "user_id": uid, "ts": now.isoformat(), "language": lang, "plan": current_plan, "source": source, "campaign": campaign, "trigger": trigger, "context": safe}
    try:
        redis = await get_redis()
        pipe = redis.pipeline()
        dimensions = ("all", f"lang:{lang}", f"plan:{current_plan}", f"source:{source}")
        for dim in dimensions:
            key = f"analytics:count:{day}:{name}:{dim}"
            pipe.incr(key); pipe.expire(key, EVENT_TTL)
        stream = f"analytics:events:{day}"
        pipe.rpush(stream, json.dumps(envelope, ensure_ascii=False)); pipe.expire(stream, EVENT_TTL)
        pipe.set(f"analytics:first:{uid}:{name}", envelope["ts"], nx=True, ex=EVENT_TTL)
        if trigger:
            pipe.set(f"analytics:conversion_trigger:{uid}", trigger, ex=30 * 86400)
        await pipe.execute()
    except Exception:
        logger.warning("Analytics event skipped: %s", name, exc_info=True)


async def get_funnel_counts(day: str, events: list[str], dimension: str = "all") -> dict[str, int]:
    redis = await get_redis()
    values = await redis.mget([f"analytics:count:{day}:{event}:{dimension}" for event in events])
    return {event: int(value or 0) for event, value in zip(events, values)}


async def consume_conversion_trigger(user_id: int) -> str | None:
    redis = await get_redis()
    key = f"analytics:conversion_trigger:{user_id}"
    value = await redis.get(key)
    if value:
        await redis.delete(key)
    return value

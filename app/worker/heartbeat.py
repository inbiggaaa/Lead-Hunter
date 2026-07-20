"""Heartbeat: periodic check that the worker event loop is alive."""

import asyncio
import logging
import time

from app.config import settings
from app.cache import get_redis

logger = logging.getLogger(__name__)

# Process-level loop liveness (not per Telethon account).
HEARTBEAT_LOOP_KEY = "heartbeat:worker:loop"
# Legacy alias kept for watchdog/RECOVERY during transition.
HEARTBEAT_KEY = "heartbeat:userbot:1"


def heartbeat_account_key(account_id: int) -> str:
    """Per-account wall-clock liveness written by the poller path."""
    return f"heartbeat:userbot:{account_id}"


async def send_heartbeat(account_ids: list[int] | None = None) -> None:
    """Refresh loop heartbeat and optional per-account wall timestamps."""
    redis = await get_redis()
    ttl = settings.heartbeat_interval_minutes * 60 * 2
    now_mono = str(asyncio.get_event_loop().time())
    now_wall = str(int(time.time()))

    await redis.set(HEARTBEAT_LOOP_KEY, now_mono)
    await redis.expire(HEARTBEAT_LOOP_KEY, ttl)
    # Keep legacy key so existing watchdog still works.
    await redis.set(HEARTBEAT_KEY, now_mono)
    await redis.expire(HEARTBEAT_KEY, ttl)
    await redis.set("heartbeat:wall:userbot:1", now_wall)
    await redis.expire("heartbeat:wall:userbot:1", ttl)

    for account_id in account_ids or []:
        key = heartbeat_account_key(account_id)
        await redis.set(key, now_wall)
        await redis.expire(key, ttl)
        await redis.set(f"heartbeat:wall:userbot:{account_id}", now_wall)
        await redis.expire(f"heartbeat:wall:userbot:{account_id}", ttl)


async def heartbeat_loop(account_ids: list[int] | None = None) -> None:
    """Periodically update heartbeat and check for stale loop heartbeats."""
    last_alert = 0.0
    alert_cooldown = 3600

    while True:
        await send_heartbeat(account_ids)
        logger.debug("Heartbeat sent")

        loop = asyncio.get_event_loop()
        now = loop.time()
        redis = await get_redis()
        stored = await redis.get(HEARTBEAT_LOOP_KEY) or await redis.get(HEARTBEAT_KEY)

        if stored:
            stored_time = float(stored)
            if now - stored_time > settings.heartbeat_interval_minutes * 60 * 3:
                if now - last_alert > alert_cooldown:
                    logger.warning("Heartbeat STALE — alerting admin")
                    from app.worker.notify_admin import notify_admin
                    await notify_admin(
                        "⚠️ LeadHunter heartbeat просрочен! Worker event loop возможно упал."
                    )
                    last_alert = now

        await asyncio.sleep(settings.heartbeat_interval_minutes * 60)

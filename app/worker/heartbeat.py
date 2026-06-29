"""Heartbeat: periodic check that userbot is alive."""

import asyncio
import logging

from app.config import settings
from app.cache import get_redis
from app.cache.subscription_cache import HEARTBEAT_KEY

logger = logging.getLogger(__name__)


async def send_heartbeat():
    """Set heartbeat timestamp in Redis."""
    redis = await get_redis()
    await redis.set(HEARTBEAT_KEY, str(asyncio.get_event_loop().time()))
    await redis.expire(HEARTBEAT_KEY, settings.heartbeat_interval_minutes * 60 * 2)
    await redis.close()


async def heartbeat_loop():
    """Periodically update heartbeat. Runs as background task."""
    while True:
        await send_heartbeat()
        logger.debug("Heartbeat sent")
        await asyncio.sleep(settings.heartbeat_interval_minutes * 60)

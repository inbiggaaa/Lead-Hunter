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
    """Periodically update heartbeat and check for stale heartbeats."""
    last_alert = 0.0
    alert_cooldown = 3600  # 1 hour between alerts

    while True:
        await send_heartbeat()
        logger.debug("Heartbeat sent")

        # Check for stale heartbeat (own check — external monitoring recommended)
        loop = asyncio.get_event_loop()
        now = loop.time()

        from app.cache import get_redis
        redis = await get_redis()
        stored = await redis.get(HEARTBEAT_KEY)
        await redis.close()

        if stored:
            stored_time = float(stored)
            if now - stored_time > settings.heartbeat_interval_minutes * 60 * 3:
                if now - last_alert > alert_cooldown:
                    logger.warning("Heartbeat STALE — alerting owner")
                    await _alert_owner("⚠️ LeadHunter heartbeat is stale! Userbot may be down.")
                    last_alert = now

        await asyncio.sleep(settings.heartbeat_interval_minutes * 60)


async def _alert_owner(text: str):
    """Send alert to owner via Bot API."""
    try:
        from aiogram import Bot
        from app.config import settings
        bot = Bot(token=settings.bot_token)
        await bot.send_message(settings.owner_telegram_id, text)
        await bot.session.close()
    except Exception:
        logger.exception("Failed to alert owner")

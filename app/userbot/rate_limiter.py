"""Centralized Telegram API rate limiter with circuit breaker.

Ensures a single account never exceeds safe request rates, regardless of how
many concurrent consumers (poller, discovery) are active.

Token bucket: 1 token every 3 seconds (20 req/min max).
Circuit breaker: opens on any FloodWait — blocks ALL API calls until expiry.
"""

import asyncio
import logging
import time

from app.cache import get_redis

logger = logging.getLogger(__name__)

# ── Redis keys ──
CIRCUIT_BREAKER_KEY = "circuit:open"
CIRCUIT_EXPIRES_KEY = "circuit:expires_at"
RATE_LIMIT_KEY = "rate:last_request_at"

# ── Defaults (override via .env) ──
DEFAULT_MIN_INTERVAL = 3.0   # seconds between API calls
DEFAULT_MAX_BURST = 2        # max consecutive calls before enforced wait


async def _now() -> float:
    return time.monotonic()


class TelegramRateLimiter:
    """Token-bucket rate limiter shared across all userbot consumers."""

    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        self.min_interval = min_interval
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available to make one Telegram API call."""
        async with self._lock:
            elapsed = await _now() - self._last_call
            if elapsed < self.min_interval:
                wait = self.min_interval - elapsed
                logger.debug("Rate limiter: waiting %.1fs", wait)
                await asyncio.sleep(wait)
            self._last_call = await _now()

    async def report_flood_wait(self, seconds: int, context: str = "") -> None:
        """Called when any FloodWait is received — opens circuit breaker."""
        redis = await get_redis()
        expires_at = int(time.time() + seconds + 10)  # 10s safety margin
        await redis.set(CIRCUIT_BREAKER_KEY, "1")
        await redis.set(CIRCUIT_EXPIRES_KEY, str(expires_at))
        await redis.expire(CIRCUIT_BREAKER_KEY, seconds + 60)
        await redis.expire(CIRCUIT_EXPIRES_KEY, seconds + 60)
        await redis.close()

        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        duration = f"{hours}ч {mins}м" if hours else f"{mins} мин"

        logger.error(
            "🚨 CIRCUIT BREAKER OPEN — FloodWait %ds from '%s'. All API calls blocked for %ds.",
            seconds, context, seconds + 10,
        )

        from app.worker.notify_admin import notify_admin
        await notify_admin(
            f"🚨 FloodWait — userbot заблокирован\n\n"
            f"⏱ Бан на: {duration}\n"
            f"📍 Источник: {context}\n"
            f"🛑 Все API-вызовы остановлены до истечения бана."
        )

    async def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently blocking requests."""
        redis = await get_redis()
        val = await redis.get(CIRCUIT_BREAKER_KEY)
        await redis.close()
        return val is not None

    async def wait_if_circuit_open(self) -> bool:
        """If circuit is open, wait until it closes. Returns True if we had to wait."""
        redis = await get_redis()
        val = await redis.get(CIRCUIT_BREAKER_KEY)
        if val:
            expires_raw = await redis.get(CIRCUIT_EXPIRES_KEY)
            await redis.close()
            if expires_raw:
                wait_until = int(expires_raw)
                remaining = wait_until - int(time.time())
                if remaining > 0:
                    logger.info("Circuit breaker: waiting %ds before any API call", remaining)
                    await asyncio.sleep(remaining)
            # Circuit breaker just closed — notify recovery
            logger.info("Circuit breaker closed — resuming API calls")
            from app.worker.notify_admin import notify_admin
            await notify_admin("✅ FloodWait истёк — userbot возобновил работу. Уведомления снова поступают.")
            return True
        await redis.close()
        return False


# Singleton for the worker process
limiter = TelegramRateLimiter()

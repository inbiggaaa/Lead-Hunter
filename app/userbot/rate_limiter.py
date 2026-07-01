"""Centralized Telegram API rate limiter with circuit breaker.

Ensures a single account never exceeds safe request rates, regardless of how
many concurrent consumers (poller, discovery) are active.

Token bucket: ~3 rps per account.
Circuit breaker: per-account — opens on FloodWait for one account,
blocks only that account's API calls until expiry.
Keys: circuit:open:{account_id}, circuit:expires:{account_id}
"""

import asyncio
import logging
import time

from app.cache import get_redis

logger = logging.getLogger(__name__)

# ── Redis keys ──
def _circuit_key(account_id: int) -> str:
    return f"circuit:open:{account_id}"

def _circuit_expires_key(account_id: int) -> str:
    return f"circuit:expires:{account_id}"
RATE_LIMIT_KEY = "rate:last_request_at"

# ── Defaults (override via .env) ──
DEFAULT_MIN_INTERVAL = 0.3   # seconds between API calls (~3 rps, safe for Telegram)
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

    async def report_flood_wait(self, seconds: int, context: str = "", account_id: int = 0) -> None:
        """Called when FloodWait is received for an account — opens its circuit breaker.

        account_id=0 means global (all accounts), used for backward compat.
        """
        redis = await get_redis()
        expires_at = int(time.time() + seconds + 10)  # 10s safety margin
        await redis.set(_circuit_key(account_id), "1")
        await redis.set(_circuit_expires_key(account_id), str(expires_at))
        await redis.expire(_circuit_key(account_id), seconds + 60)
        await redis.expire(_circuit_expires_key(account_id), seconds + 60)
        await redis.close()

        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        duration = f"{hours}ч {mins}м" if hours else f"{mins} мин"

        logger.error(
            "🚨 CIRCUIT BREAKER OPEN (account %d) — FloodWait %ds from '%s'. Blocked for %ds.",
            account_id, seconds, context, seconds + 10,
        )

        from app.worker.notify_admin import notify_admin
        await notify_admin(
            f"🚨 FloodWait — аккаунт #{account_id} заблокирован\n\n"
            f"⏱ Бан на: {duration}\n"
            f"📍 Источник: {context}\n"
            f"🛑 API-вызовы аккаунта #{account_id} остановлены до истечения бана."
        )

    async def is_circuit_open(self, account_id: int = 0) -> bool:
        """Check if circuit breaker is currently blocking requests for an account.

        account_id=0 checks the legacy global key (backward compat).
        """
        redis = await get_redis()
        # Also check legacy global key for backward compat
        if account_id == 0:
            val = await redis.get("circuit:open")
            if val:
                await redis.close()
                return True
        val = await redis.get(_circuit_key(account_id))
        await redis.close()
        return val is not None

    async def is_any_circuit_open(self) -> bool:
        """Check if ANY account has an open circuit breaker."""
        redis = await get_redis()
        # Check legacy global key
        val = await redis.get("circuit:open")
        if val:
            await redis.close()
            return True
        # Scan for any per-account keys
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="circuit:open:*", count=10)
            if keys:
                await redis.close()
                return True
            if cursor == 0:
                break
        await redis.close()
        return False

    async def wait_if_circuit_open(self, account_id: int = 0) -> bool:
        """If circuit is open for this account, wait until it closes.

        account_id=0 means check legacy global key + all accounts (block until all clear).
        Returns True if we had to wait.
        """
        redis = await get_redis()
        key = _circuit_key(account_id)
        expires_key = _circuit_expires_key(account_id)

        # Also check legacy global key
        global_val = await redis.get("circuit:open")
        val = await redis.get(key)

        if not val and not global_val:
            await redis.close()
            return False

        # Find the longest wait needed
        max_remaining = 0

        for check_key, check_expires_key in [
            ("circuit:open", "circuit:expires_at"),
            (key, expires_key),
        ]:
            check_val = await redis.get(check_key)
            if check_val:
                expires_raw = await redis.get(check_expires_key)
                if expires_raw:
                    wait_until = int(expires_raw)
                    remaining = wait_until - int(time.time())
                    if remaining > max_remaining:
                        max_remaining = remaining

        if max_remaining > 0:
            logger.info(
                "Circuit breaker (account %d): waiting %ds before API call",
                account_id, max_remaining,
            )
            await asyncio.sleep(max_remaining)

        # Circuit breaker just closed — notify recovery
        logger.info("Circuit breaker closed for account %d — resuming API calls", account_id)
        from app.worker.notify_admin import notify_admin
        await notify_admin(
            f"✅ FloodWait истёк для аккаунта #{account_id} — работа возобновлена."
        )
        # Clear keys to prevent duplicate notifications
        await redis.delete(key, expires_key, "circuit:open", "circuit:expires_at")
        await redis.close()
        return True


# Singleton for the worker process
limiter = TelegramRateLimiter()

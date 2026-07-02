"""Centralized Telegram API rate limiter with circuit breaker.

Ensures a single account never exceeds safe request rates, regardless of how
many concurrent consumers (poller, discovery) are active.

Per-account token bucket + daily budget.
Circuit breaker: per-account — opens on FloodWait for one account,
blocks only that account's API calls until expiry.
Keys:
  circuit:open:{account_id}, circuit:expires:{account_id}
  budget:used:{account_id}:{YYYY-MM-DD}
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from app.cache import get_redis

logger = logging.getLogger(__name__)

# ── Redis keys ──
def _circuit_key(account_id: int) -> str:
    return f"circuit:open:{account_id}"

def _circuit_expires_key(account_id: int) -> str:
    return f"circuit:expires:{account_id}"

def _budget_key(account_id: int) -> str:
    """Daily budget key — date in the key name, reset by date change."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:used:{account_id}:{today}"

class BudgetExceeded(Exception):
    """Raised when an account exceeds its daily API request budget."""

    def __init__(self, account_id: int, used: int, limit: int):
        self.account_id = account_id
        self.used = used
        self.limit = limit
        super().__init__(
            f"Account {account_id}: daily budget exceeded ({used}/{limit})"
        )


async def _now() -> float:
    return time.monotonic()


class TelegramRateLimiter:
    """Per-account token-bucket rate limiter with daily budget."""

    def __init__(self, min_interval: float, daily_budget: int):
        self.min_interval = min_interval
        self.daily_budget = daily_budget
        # Per-account state — each account gets its own timer and lock
        self._account_last_call: dict[int, float] = {}
        self._account_locks: dict[int, asyncio.Lock] = {}
        # Post-ban cache: {account_id: (checked_at_ts, is_active)}
        self._post_ban_cache: dict[int, tuple[float, bool]] = {}

    async def acquire(self, account_id: int) -> None:
        """Wait for per-account rate limit slot, then check and increment daily budget.

        Raises BudgetExceeded if the account has used all its daily API calls.
        """
        # 1. Check daily budget BEFORE waiting on interval.
        #    account_id=0 is legacy (discovery v1 on pause) — gets its own key,
        #    harmless since v1 is not actively running.
        if self.daily_budget > 0:
            effective_budget = self.daily_budget
            if await self._is_post_ban(account_id):
                effective_budget = max(1, self.daily_budget // 2)
            redis = await get_redis()
            try:
                key = _budget_key(account_id)
                used = await redis.incr(key)
                if used == 1:
                    # First use today — set TTL for cleanup (2 days)
                    await redis.expire(key, 172800)
                if used > effective_budget:
                    raise BudgetExceeded(account_id, used, effective_budget)
            finally:
                await redis.aclose()

        # 2. Per-account rate limiting
        lock = self._get_lock(account_id)
        async with lock:
            now = await _now()
            last = self._account_last_call.get(account_id, 0.0)
            elapsed = now - last
            if elapsed < self.min_interval:
                wait = self.min_interval - elapsed
                await asyncio.sleep(wait)
            self._account_last_call[account_id] = await _now()

    async def budget_remaining(self, account_id: int) -> int:
        """Return remaining budget for this account today, or -1 if budget disabled."""
        if self.daily_budget <= 0:
            return -1
        redis = await get_redis()
        try:
            key = _budget_key(account_id)
            raw = await redis.get(key)
            used = int(raw) if raw else 0
            return max(0, self.daily_budget - used)
        finally:
            await redis.aclose()

    async def _is_post_ban(self, account_id: int) -> bool:
        """Check if account is in post-ban mode. Cached for 60s to avoid Redis
        on every API call in hot path."""
        cached = self._post_ban_cache.get(account_id)
        now = time.time()
        if cached and (now - cached[0]) < 60:
            return cached[1]

        redis = await get_redis()
        val = await redis.get(f"post_ban_until:{account_id}")
        await redis.aclose()
        active = val is not None and now < float(val)
        self._post_ban_cache[account_id] = (now, active)
        return active

    async def activate_post_ban_if_recent(self, account_id: int) -> bool:
        """Activate post-ban if account was banned < 48h ago and post_ban
        not already active. Idempotent — won't overwrite existing post_ban.

        Layer 3: called at worker startup for accounts whose CB expired
        while the worker was down.
        """
        redis = await get_redis()
        try:
            existing = await redis.get(f"post_ban_until:{account_id}")
            if existing and time.time() < float(existing):
                return False

            last_ban = await redis.get(f"last_ban_at:{account_id}")
            if not last_ban:
                return False

            ban_ago = time.time() - float(last_ban)
            if ban_ago > 48 * 3600:
                return False

            until = int(time.time() + 48 * 3600)
            await redis.set(f"post_ban_until:{account_id}", str(until))
            await redis.expire(f"post_ban_until:{account_id}", 52 * 3600)
            logger.info(
                "Account %d: post-ban activated for 48h (was banned %.1fh ago at startup)",
                account_id, ban_ago / 3600,
            )
            return True
        finally:
            await redis.aclose()

    def _get_lock(self, account_id: int) -> asyncio.Lock:
        """Get or create a per-account asyncio.Lock."""
        if account_id not in self._account_locks:
            self._account_locks[account_id] = asyncio.Lock()
        return self._account_locks[account_id]

    # ── Circuit breaker (unchanged — already per-account) ──

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
        # Record last_ban_at for post_ban activation at worker restart (layer 1)
        last_ban_key = f"last_ban_at:{account_id}"
        await redis.set(last_ban_key, str(int(time.time())))
        await redis.expire(last_ban_key, seconds + 48 * 3600)
        await redis.aclose()

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
                await redis.aclose()
                return True
        val = await redis.get(_circuit_key(account_id))
        await redis.aclose()
        return val is not None

    async def is_any_circuit_open(self) -> bool:
        """Check if ANY account has an open circuit breaker."""
        redis = await get_redis()
        # Check legacy global key
        val = await redis.get("circuit:open")
        if val:
            await redis.aclose()
            return True
        # Scan for any per-account keys
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="circuit:open:*", count=10)
            if keys:
                await redis.aclose()
                return True
            if cursor == 0:
                break
        await redis.aclose()
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
            await redis.aclose()
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

        # Activate post-ban mode for 48h (layer 2: worker was running during CB)
        post_ban_key = f"post_ban_until:{account_id}"
        await redis.set(post_ban_key, str(int(time.time()) + 48 * 3600))
        await redis.expire(post_ban_key, 52 * 3600)

        from app.worker.notify_admin import notify_admin
        await notify_admin(
            f"✅ FloodWait истёк для аккаунта #{account_id} — работа возобновлена.\n\n"
            f"🛡 Пост-бан режим активирован на 48ч (бюджет 50%, интервалы ×1.5)"
        )
        # Clear keys to prevent duplicate notifications
        await redis.delete(key, expires_key, "circuit:open", "circuit:expires_at")
        await redis.aclose()
        return True


# Singleton for the worker process — reads config values
from app.config import settings

limiter = TelegramRateLimiter(
    min_interval=settings.userbot_min_interval,
    daily_budget=settings.daily_request_budget,
)

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

def _ban_count_key(account_id: int) -> str:
    """Rolling ban counter — incremented on each FloodWait, TTL 7 days."""
    return f"ban_count:{account_id}"

class BudgetExceeded(Exception):
    """Raised when an account exceeds its daily API request budget."""

    def __init__(self, account_id: int, used: int, limit: int):
        self.account_id = account_id
        self.used = used
        self.limit = limit
        super().__init__(
            f"Account {account_id}: daily budget exceeded ({used}/{limit})"
        )


class CircuitBreakerOpenError(Exception):
    """Raised when acquire() is called while circuit breaker is open for this account."""

    def __init__(self, account_id: int):
        self.account_id = account_id
        super().__init__(
            f"Circuit breaker open for account {account_id} — API calls blocked"
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
        # Ban count cache: {account_id: count} — co-cached with _is_post_ban
        self._ban_count_cache: dict[int, int] = {}

    async def acquire(self, account_id: int) -> None:
        """Wait for per-account rate limit slot, then check and increment daily budget.

        Raises BudgetExceeded if the account has used all its daily API calls.

        Note: Circuit breaker check is NOT done here — that is the caller's
        responsibility (_distribute and _poll_batch gate at the tier/batch level).
        This method concerns itself only with rate limiting and budget.
        """
        # 1. Check daily budget BEFORE waiting on interval.
        #    account_id=0 is legacy (discovery v1 on pause) — gets its own key,
        #    harmless since v1 is not actively running.
        if self.daily_budget > 0:
            effective_budget = self.daily_budget
            if await self._is_post_ban(account_id):
                ban_count = await self.get_ban_count(account_id)
                divisor = self._ban_budget_divisor(ban_count)
                effective_budget = max(1, self.daily_budget // divisor)
            redis = await get_redis()
            key = _budget_key(account_id)
            used = await redis.incr(key)
            if used == 1:
                # First use today — set TTL for cleanup (2 days)
                await redis.expire(key, 172800)
            if used > effective_budget:
                raise BudgetExceeded(account_id, used, effective_budget)

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
        key = _budget_key(account_id)
        raw = await redis.get(key)
        used = int(raw) if raw else 0
        return max(0, self.daily_budget - used)

    async def get_ban_count(self, account_id: int) -> int:
        """Return number of FloodWait bans in the last 7 days.

        Cached in _post_ban_cache alongside _is_post_ban result —
        avoids Redis on every acquire() in post-ban mode.
        """
        # Check cache first (piggybacks on _is_post_ban cache structure)
        cached = self._post_ban_cache.get(account_id)
        now = time.time()
        if cached and (now - cached[0]) < 60:
            # ban_count is stored in a second cache dict
            bc = self._ban_count_cache.get(account_id)
            if bc is not None:
                return bc

        redis = await get_redis()
        raw = await redis.get(_ban_count_key(account_id))
        count = int(raw) if raw else 0
        self._ban_count_cache[account_id] = count
        return count

    def _ban_budget_divisor(self, ban_count: int) -> int:
        """Escalating budget divisor: 1→2, 2→4, 3+→8."""
        return {1: 2, 2: 4}.get(ban_count, 8)

    def _ban_interval_multiplier(self, ban_count: int) -> float:
        """Escalating interval multiplier: 1→1.5, 2→3.0, 3+→5.0."""
        return {1: 1.5, 2: 3.0}.get(ban_count, 5.0)

    async def get_post_ban_interval_multiplier(self, account_id: int) -> float:
        """Get the interval multiplier for this account based on its ban count.

        Returns 1.0 if account is not in post-ban mode.
        Returns escalating multiplier based on number of bans in last 7 days.
        """
        if not await self._is_post_ban(account_id):
            return 1.0
        ban_count = await self.get_ban_count(account_id)
        return self._ban_interval_multiplier(ban_count)

    async def _is_post_ban(self, account_id: int) -> bool:
        """Check if account is in post-ban mode. Cached for 60s to avoid Redis
        on every API call in hot path."""
        cached = self._post_ban_cache.get(account_id)
        now = time.time()
        if cached and (now - cached[0]) < 60:
            return cached[1]

        redis = await get_redis()
        val = await redis.get(f"post_ban_until:{account_id}")
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

        # Increment rolling ban counter (TTL 7 days — auto-resets if no more bans)
        ban_count = await redis.incr(_ban_count_key(account_id))
        await redis.expire(_ban_count_key(account_id), 7 * 86400)

        # Throttle admin notifications — same account, same ban = one alert per 15min.
        # Without this, multiple concurrent FloodWait catches (different tiers)
        # would spam notify_admin before circuit breaker propagates.
        alert_key = f"alert:last:flood_wait_report:{account_id}"
        last_alert = await redis.get(alert_key)
        should_alert = not last_alert or (time.time() - float(last_alert)) >= 900
        if should_alert:
            await redis.set(alert_key, str(time.time()))

        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        duration = f"{hours}ч {mins}м" if hours else f"{mins} мин"

        logger.error(
            "🚨 CIRCUIT BREAKER OPEN (account %d) — FloodWait %ds from '%s'. Blocked for %ds.",
            account_id, seconds, context, seconds + 10,
        )

        if should_alert:
            divisor = self._ban_budget_divisor(ban_count)
            multiplier = self._ban_interval_multiplier(ban_count)
            budget_pct = int(100 / divisor)
            esc_info = (
                f"📊 Это бан #{ban_count} за 7 дней\n"
                f"🛡 После снятия: бюджет {budget_pct}%, интервалы ×{multiplier}"
            )
            perm_risk = ""
            if ban_count >= 3:
                perm_risk = (
                    f"\n\n⚠️ РИСК ПЕРМАНЕНТНОГО БАНА — "
                    f"{ban_count} бана за 7 дней. Рассмотрите замену аккаунта."
                )

            from app.worker.notify_admin import notify_admin
            await notify_admin(
                f"🚨 FloodWait — аккаунт #{account_id} заблокирован\n\n"
                f"⏱ Бан на: {duration}\n"
                f"📍 Источник: {context}\n"
                f"{esc_info}\n"
                f"🛑 API-вызовы аккаунта #{account_id} остановлены до истечения бана."
                f"{perm_risk}"
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
                return True
        val = await redis.get(_circuit_key(account_id))
        return val is not None

    async def is_any_circuit_open(self) -> bool:
        """Check if ANY account has an open circuit breaker."""
        redis = await get_redis()
        # Check legacy global key
        val = await redis.get("circuit:open")
        if val:
            return True
        # Scan for any per-account keys
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="circuit:open:*", count=10)
            if keys:
                return True
            if cursor == 0:
                break
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

        ban_count = await self.get_ban_count(account_id)
        divisor = self._ban_budget_divisor(ban_count)
        multiplier = self._ban_interval_multiplier(ban_count)
        budget_pct = int(100 / divisor)

        from app.worker.notify_admin import notify_admin
        notify_text = (
            f"✅ FloodWait истёк для аккаунта #{account_id} — работа возобновлена.\n\n"
            f"🛡 Пост-бан режим активирован на 48ч\n"
            f"📊 Бан #{ban_count} за 7 дней: бюджет {budget_pct}%, интервалы ×{multiplier}"
        )
        if ban_count >= 3:
            notify_text += (
                f"\n\n⚠️ Аккаунт #{account_id} получил {ban_count} бана за 7 дней — "
                f"РИСК ПЕРМАНЕНТНОГО БАНА. Рассмотрите замену аккаунта."
            )
        await notify_admin(notify_text)
        # Clear keys to prevent duplicate notifications
        await redis.delete(key, expires_key, "circuit:open", "circuit:expires_at")
        return True


# Singleton for the worker process — reads config values
from app.config import settings

limiter = TelegramRateLimiter(
    min_interval=settings.userbot_min_interval,
    daily_budget=settings.daily_request_budget,
)

"""Centralized Telegram API rate limiter with circuit breaker and capacity governor.

Per-account token bucket + daily budget + Redis RPC metrics + governor state.
Circuit breaker: per-account — opens on FloodWait for one account.
Governor: COOLDOWN → RECOVERY after deadline; power=0 blocks acquire().

Keys:
  circuit:open:{account_id}, circuit:expires:{account_id}
  budget:used:{account_id}:{YYYY-MM-DD}
  userbot:governor:{account_id}
  stats:tg_rpc:{account_id}:minute|hour|day:{stamp}
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from app.cache import get_redis
from app.config import settings
from app.userbot.capacity import (
    FloodSeverity,
    GovernorSnapshot,
    GovernorState,
    classify_flood,
    recovery_plan,
)

logger = logging.getLogger(__name__)

_COOLDOWN_BUFFER_SECONDS = 10
_COOLDOWN_JITTER_SECONDS = 30
_MINUTE_TTL = 2 * 86400
_HOUR_TTL = 8 * 86400
_DAY_TTL = 30 * 86400
_RPC_KINDS = frozenset({"get_history", "resolve", "health"})


def _circuit_key(account_id: int) -> str:
    return f"circuit:open:{account_id}"


def _circuit_expires_key(account_id: int) -> str:
    return f"circuit:expires:{account_id}"


def _budget_key(account_id: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"budget:used:{account_id}:{today}"


def _ban_count_key(account_id: int) -> str:
    return f"ban_count:{account_id}"


def _governor_key(account_id: int) -> str:
    return f"userbot:governor:{account_id}"


def _rpc_bucket_keys(account_id: int, now: datetime | None = None) -> tuple[str, str, str]:
    stamp = now or datetime.now(timezone.utc)
    minute = stamp.strftime("%Y%m%d%H%M")
    hour = stamp.strftime("%Y%m%d%H")
    day = stamp.strftime("%Y%m%d")
    return (
        f"stats:tg_rpc:{account_id}:minute:{minute}",
        f"stats:tg_rpc:{account_id}:hour:{hour}",
        f"stats:tg_rpc:{account_id}:day:{day}",
    )


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
    """Raised when acquire() is called while circuit breaker is open."""

    def __init__(self, account_id: int):
        self.account_id = account_id
        super().__init__(
            f"Circuit breaker open for account {account_id} — API calls blocked"
        )


class GovernorBlocked(Exception):
    """Raised when governor forbids Telegram RPC for an account."""

    def __init__(self, account_id: int, retry_at: int, state: GovernorState):
        self.account_id = account_id
        self.retry_at = retry_at
        self.state = state
        super().__init__(
            f"Governor blocked account {account_id} in {state} until {retry_at}"
        )


async def _now() -> float:
    return time.monotonic()


def _default_snapshot(account_id: int) -> GovernorSnapshot:
    return GovernorSnapshot(
        account_id=account_id,
        state=GovernorState.NORMAL,
        power_percent=100,
        recommended_state=GovernorState.NORMAL,
        recommended_power_percent=100,
        severity=None,
        cooldown_until=None,
        stage_index=None,
        stage_until=None,
        stable_windows=0,
        last_flood_at=None,
        last_flood_seconds=0,
        last_rpc_at=None,
        continuous_started_at=None,
    )


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    return int(raw)


def _parse_severity(raw: str | None) -> FloodSeverity | None:
    if not raw:
        return None
    return FloodSeverity(raw)


def _snapshot_from_hash(account_id: int, data: dict[str, str]) -> GovernorSnapshot:
    if not data:
        return _default_snapshot(account_id)
    return GovernorSnapshot(
        account_id=account_id,
        state=GovernorState(data.get("state", GovernorState.NORMAL)),
        power_percent=int(data.get("power_percent", "100")),
        recommended_state=GovernorState(
            data.get("recommended_state", data.get("state", GovernorState.NORMAL))
        ),
        recommended_power_percent=int(
            data.get("recommended_power_percent", data.get("power_percent", "100"))
        ),
        severity=_parse_severity(data.get("severity")),
        cooldown_until=_parse_optional_int(data.get("cooldown_until")),
        stage_index=_parse_optional_int(data.get("stage_index")),
        stage_until=_parse_optional_int(data.get("stage_until")),
        stable_windows=int(data.get("stable_windows", "0")),
        last_flood_at=_parse_optional_int(data.get("last_flood_at")),
        last_flood_seconds=int(data.get("last_flood_seconds", "0")),
        last_rpc_at=_parse_optional_int(data.get("last_rpc_at")),
        continuous_started_at=_parse_optional_int(data.get("continuous_started_at")),
    )


def _snapshot_to_mapping(snapshot: GovernorSnapshot) -> dict[str, str]:
    return {
        "state": snapshot.state.value,
        "power_percent": str(snapshot.power_percent),
        "recommended_state": snapshot.recommended_state.value,
        "recommended_power_percent": str(snapshot.recommended_power_percent),
        "severity": snapshot.severity.value if snapshot.severity else "",
        "cooldown_until": "" if snapshot.cooldown_until is None else str(snapshot.cooldown_until),
        "stage_index": "" if snapshot.stage_index is None else str(snapshot.stage_index),
        "stage_until": "" if snapshot.stage_until is None else str(snapshot.stage_until),
        "stable_windows": str(snapshot.stable_windows),
        "last_flood_at": "" if snapshot.last_flood_at is None else str(snapshot.last_flood_at),
        "last_flood_seconds": str(snapshot.last_flood_seconds),
        "last_rpc_at": "" if snapshot.last_rpc_at is None else str(snapshot.last_rpc_at),
        "continuous_started_at": (
            "" if snapshot.continuous_started_at is None
            else str(snapshot.continuous_started_at)
        ),
    }


class TelegramRateLimiter:
    """Per-account token-bucket rate limiter with daily budget and governor."""

    def __init__(self, min_interval: float, daily_budget: int):
        self.min_interval = min_interval
        self.daily_budget = daily_budget
        self._account_last_call: dict[int, float] = {}
        self._account_locks: dict[int, asyncio.Lock] = {}
        self._post_ban_cache: dict[int, tuple[float, bool]] = {}
        self._ban_count_cache: dict[int, int] = {}

    async def _redis(self, account_id: int = 0):
        try:
            return await get_redis()
        except Exception as exc:
            raise GovernorBlocked(
                account_id=account_id,
                retry_at=int(time.time()) + 60,
                state=GovernorState.OFFLINE,
            ) from exc

    async def acquire(self, account_id: int, rpc_kind: str = "get_history") -> None:
        """Wait for rate slot, check governor/budget, record attempt."""
        kind = rpc_kind if rpc_kind in _RPC_KINDS else "get_history"
        try:
            snapshot = await self.refresh_governor(account_id)
        except GovernorBlocked:
            raise
        except Exception as exc:
            raise GovernorBlocked(
                account_id=account_id,
                retry_at=int(time.time()) + 60,
                state=GovernorState.OFFLINE,
            ) from exc

        self._raise_if_blocked(account_id, snapshot)
        await self._enforce_budget(account_id)
        await self._wait_interval(account_id, snapshot.power_percent)
        await self._record_attempt(account_id, kind)
        await self._touch_rpc_timestamps(account_id, snapshot)

    def _raise_if_blocked(self, account_id: int, snapshot: GovernorSnapshot) -> None:
        blocked_states = {
            GovernorState.COOLDOWN,
            GovernorState.QUARANTINED,
            GovernorState.OFFLINE,
        }
        if snapshot.state in blocked_states or snapshot.power_percent <= 0:
            retry_at = snapshot.cooldown_until or snapshot.stage_until or int(time.time()) + 60
            raise GovernorBlocked(account_id, retry_at, snapshot.state)

    async def _enforce_budget(self, account_id: int) -> None:
        if self.daily_budget <= 0:
            return
        effective_budget = self.daily_budget
        if await self._is_post_ban(account_id):
            ban_count = await self.get_ban_count(account_id)
            divisor = self._ban_budget_divisor(ban_count)
            effective_budget = max(1, self.daily_budget // divisor)
        redis = await self._redis()
        key = _budget_key(account_id)
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, 172800)
        if used > effective_budget:
            raise BudgetExceeded(account_id, used, effective_budget)

    async def _wait_interval(self, account_id: int, power_percent: int) -> None:
        interval = self.min_interval * (100.0 / max(power_percent, 1))
        lock = self._get_lock(account_id)
        async with lock:
            now = await _now()
            last = self._account_last_call.get(account_id, 0.0)
            elapsed = now - last
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            self._account_last_call[account_id] = await _now()

    async def _record_attempt(self, account_id: int, rpc_kind: str) -> None:
        if not settings.userbot_rpc_metrics_enabled:
            return
        await self._incr_rpc_fields(account_id, ("total", "attempt", rpc_kind))

    async def record_rpc_result(
        self,
        account_id: int,
        rpc_kind: str,
        outcome: str,
    ) -> None:
        """Record success/error/flood_wait outcome for RPC metrics."""
        if not settings.userbot_rpc_metrics_enabled:
            return
        fields = [outcome] if outcome in {"success", "error", "flood_wait"} else ["error"]
        await self._incr_rpc_fields(account_id, tuple(fields))

    async def _incr_rpc_fields(self, account_id: int, fields: tuple[str, ...]) -> None:
        redis = await self._redis()
        minute_key, hour_key, day_key = _rpc_bucket_keys(account_id)
        pipe = redis.pipeline()
        for key, ttl in (
            (minute_key, _MINUTE_TTL),
            (hour_key, _HOUR_TTL),
            (day_key, _DAY_TTL),
        ):
            for field in fields:
                pipe.hincrby(key, field, 1)
            pipe.expire(key, ttl)
        await pipe.execute()

    async def _touch_rpc_timestamps(
        self,
        account_id: int,
        snapshot: GovernorSnapshot,
    ) -> None:
        now = int(time.time())
        continuous = snapshot.continuous_started_at or now
        updated = GovernorSnapshot(
            account_id=snapshot.account_id,
            state=snapshot.state,
            power_percent=snapshot.power_percent,
            recommended_state=snapshot.recommended_state,
            recommended_power_percent=snapshot.recommended_power_percent,
            severity=snapshot.severity,
            cooldown_until=snapshot.cooldown_until,
            stage_index=snapshot.stage_index,
            stage_until=snapshot.stage_until,
            stable_windows=snapshot.stable_windows,
            last_flood_at=snapshot.last_flood_at,
            last_flood_seconds=snapshot.last_flood_seconds,
            last_rpc_at=now,
            continuous_started_at=continuous,
        )
        await self._save_governor(updated)

    async def get_governor_snapshot(self, account_id: int) -> GovernorSnapshot:
        redis = await self._redis()
        data = await redis.hgetall(_governor_key(account_id))
        return _snapshot_from_hash(account_id, data or {})

    async def refresh_governor(
        self,
        account_id: int,
        now: int | None = None,
    ) -> GovernorSnapshot:
        """Single source of truth for governor transitions (v1: cooldown→recovery)."""
        current = now if now is not None else int(time.time())
        snapshot = await self.get_governor_snapshot(account_id)
        updated = self._apply_governor_rules(snapshot, current)
        if updated != snapshot:
            await self._save_governor(updated)
        return updated

    def _apply_governor_rules(
        self,
        snapshot: GovernorSnapshot,
        now: int,
    ) -> GovernorSnapshot:
        if snapshot.state is GovernorState.COOLDOWN:
            if snapshot.cooldown_until is not None and now > snapshot.cooldown_until:
                return self._enter_recovery(snapshot, now)
        return snapshot

    def _enter_recovery(self, snapshot: GovernorSnapshot, now: int) -> GovernorSnapshot:
        severity = snapshot.severity or FloodSeverity.MEDIUM
        stages = recovery_plan(severity)
        first = stages[0]
        stage_until = now + first.hold_seconds if first.hold_seconds > 0 else None
        return GovernorSnapshot(
            account_id=snapshot.account_id,
            state=GovernorState.RECOVERY,
            power_percent=first.power_percent,
            recommended_state=GovernorState.RECOVERY,
            recommended_power_percent=first.power_percent,
            severity=severity,
            cooldown_until=None,
            stage_index=0,
            stage_until=stage_until,
            stable_windows=0,
            last_flood_at=snapshot.last_flood_at,
            last_flood_seconds=snapshot.last_flood_seconds,
            last_rpc_at=snapshot.last_rpc_at,
            continuous_started_at=None,
        )

    async def _save_governor(self, snapshot: GovernorSnapshot) -> None:
        redis = await self._redis()
        key = _governor_key(snapshot.account_id)
        mapping = _snapshot_to_mapping(snapshot)
        pipe = redis.pipeline()
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, 40 * 86400)
        await pipe.execute()

    async def budget_remaining(self, account_id: int) -> int:
        if self.daily_budget <= 0:
            return -1
        redis = await self._redis()
        raw = await redis.get(_budget_key(account_id))
        used = int(raw) if raw else 0
        return max(0, self.daily_budget - used)

    async def get_ban_count(self, account_id: int) -> int:
        cached = self._post_ban_cache.get(account_id)
        now = time.time()
        if cached and (now - cached[0]) < 60:
            bc = self._ban_count_cache.get(account_id)
            if bc is not None:
                return bc
        redis = await self._redis()
        raw = await redis.get(_ban_count_key(account_id))
        count = int(raw) if raw else 0
        self._ban_count_cache[account_id] = count
        return count

    def _ban_budget_divisor(self, ban_count: int) -> int:
        return {1: 2, 2: 4}.get(ban_count, 8)

    def _ban_interval_multiplier(self, ban_count: int) -> float:
        return {1: 1.5, 2: 3.0}.get(ban_count, 5.0)

    async def get_post_ban_interval_multiplier(self, account_id: int) -> float:
        if not await self._is_post_ban(account_id):
            return 1.0
        ban_count = await self.get_ban_count(account_id)
        return self._ban_interval_multiplier(ban_count)

    async def _is_post_ban(self, account_id: int) -> bool:
        cached = self._post_ban_cache.get(account_id)
        now = time.time()
        if cached and (now - cached[0]) < 60:
            return cached[1]
        redis = await self._redis()
        val = await redis.get(f"post_ban_until:{account_id}")
        active = val is not None and now < float(val)
        self._post_ban_cache[account_id] = (now, active)
        return active

    async def activate_post_ban_if_recent(self, account_id: int) -> bool:
        redis = await self._redis()
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
        if account_id not in self._account_locks:
            self._account_locks[account_id] = asyncio.Lock()
        return self._account_locks[account_id]

    async def report_flood_wait(
        self,
        seconds: int,
        context: str = "",
        account_id: int = 0,
        rpc_kind: str = "get_history",
    ) -> None:
        """Open circuit + enter COOLDOWN. Does not sleep the FloodWait duration."""
        redis = await self._redis()
        now = int(time.time())
        jitter = random.randint(0, _COOLDOWN_JITTER_SECONDS)
        cooldown_until = now + seconds + _COOLDOWN_BUFFER_SECONDS + jitter
        expires_at = cooldown_until
        await redis.set(_circuit_key(account_id), "1")
        await redis.set(_circuit_expires_key(account_id), str(expires_at))
        await redis.expire(_circuit_key(account_id), seconds + 60 + jitter)
        await redis.expire(_circuit_expires_key(account_id), seconds + 60 + jitter)
        last_ban_key = f"last_ban_at:{account_id}"
        await redis.set(last_ban_key, str(now))
        await redis.expire(last_ban_key, seconds + 48 * 3600)
        ban_count = await redis.incr(_ban_count_key(account_id))
        await redis.expire(_ban_count_key(account_id), 7 * 86400)

        severity = classify_flood(seconds)
        previous = await self.get_governor_snapshot(account_id)
        if previous.state is GovernorState.RECOVERY:
            # Repeated FloodWait rolls recovery back; keep the stricter severity.
            rank = {
                FloodSeverity.SHORT: 1,
                FloodSeverity.MEDIUM: 2,
                FloodSeverity.LONG: 3,
            }
            previous_severity = previous.severity or FloodSeverity.SHORT
            if rank[previous_severity] > rank[severity]:
                severity = previous_severity
        snapshot = GovernorSnapshot(
            account_id=account_id,
            state=GovernorState.COOLDOWN,
            power_percent=0,
            recommended_state=GovernorState.COOLDOWN,
            recommended_power_percent=0,
            severity=severity,
            cooldown_until=cooldown_until,
            stage_index=None,
            stage_until=None,
            stable_windows=0,
            last_flood_at=now,
            last_flood_seconds=seconds,
            last_rpc_at=previous.last_rpc_at,
            continuous_started_at=None,
        )
        await self._save_governor(snapshot)
        if settings.userbot_rpc_metrics_enabled:
            await self._incr_rpc_fields(
                account_id, ("total", "flood_wait", rpc_kind if rpc_kind in _RPC_KINDS else "get_history")
            )

        await self._alert_flood_wait(account_id, seconds, context, ban_count)

    async def _alert_flood_wait(
        self,
        account_id: int,
        seconds: int,
        context: str,
        ban_count: int,
    ) -> None:
        redis = await self._redis()
        alert_key = f"alert:last:flood_wait_report:{account_id}"
        last_alert = await redis.get(alert_key)
        should_alert = not last_alert or (time.time() - float(last_alert)) >= 900
        if should_alert:
            await redis.set(alert_key, str(time.time()))
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        duration = f"{hours}ч {mins}м" if hours else f"{mins} мин"
        logger.error(
            "CIRCUIT BREAKER OPEN (account %d) — FloodWait %ds from '%s'. Blocked for %ds.",
            account_id, seconds, context, seconds + _COOLDOWN_BUFFER_SECONDS,
        )
        if not should_alert:
            return
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
        redis = await self._redis()
        if account_id == 0:
            val = await redis.get("circuit:open")
            if val:
                return True
        val = await redis.get(_circuit_key(account_id))
        if val is not None:
            return True
        snapshot = await self.get_governor_snapshot(account_id)
        return snapshot.state in {
            GovernorState.COOLDOWN,
            GovernorState.QUARANTINED,
        }

    async def is_any_circuit_open(self) -> bool:
        redis = await self._redis()
        val = await redis.get("circuit:open")
        if val:
            return True
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match="circuit:open:*", count=10)
            if keys:
                return True
            if cursor == 0:
                break
        return False

    async def wait_if_circuit_open(self, account_id: int = 0) -> bool:
        redis = await self._redis()
        key = _circuit_key(account_id)
        expires_key = _circuit_expires_key(account_id)
        global_val = await redis.get("circuit:open")
        val = await redis.get(key)
        if not val and not global_val:
            return False

        max_remaining = 0
        for check_key, check_expires_key in [
            ("circuit:open", "circuit:expires_at"),
            (key, expires_key),
        ]:
            check_val = await redis.get(check_key)
            if not check_val:
                continue
            expires_raw = await redis.get(check_expires_key)
            if not expires_raw:
                continue
            remaining = int(expires_raw) - int(time.time())
            if remaining > max_remaining:
                max_remaining = remaining

        if max_remaining > 0:
            logger.info(
                "Circuit breaker (account %d): waiting %ds before API call",
                account_id, max_remaining,
            )
            await asyncio.sleep(max_remaining)

        logger.info("Circuit breaker closed for account %d — resuming API calls", account_id)
        post_ban_key = f"post_ban_until:{account_id}"
        await redis.set(post_ban_key, str(int(time.time()) + 48 * 3600))
        await redis.expire(post_ban_key, 52 * 3600)
        await self.refresh_governor(account_id)
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
        await redis.delete(key, expires_key, "circuit:open", "circuit:expires_at")
        return True


limiter = TelegramRateLimiter(
    min_interval=settings.userbot_min_interval,
    daily_budget=settings.daily_request_budget,
)

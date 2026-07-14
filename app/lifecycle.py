"""No-subscription lifecycle: sparse lead teasers, reports, and winback offer."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.cache import get_redis
from app.db.models import User
from app.db.session import async_session_factory

TEASER_DAYS = frozenset({0, 3, 7, 14})
TEASERS_PER_DAY = 2
OFFER_DAY = 30
OFFER_DISCOUNT = 0.25
OFFER_HOURS = 12


def lifecycle_day(anchor: datetime, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return max(0, (now.date() - anchor.astimezone(timezone.utc).date()).days)


async def ensure_free_lifecycle(user_id: int, now: datetime | None = None) -> datetime | None:
    """Return a persistent lifecycle anchor, creating it on the first Free match."""
    now = now or datetime.now(timezone.utc)
    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            return None
        if user.plan != "free":
            if not user.plan_expires_at or user.plan_expires_at > now:
                return None
            user.plan = "free"
        anchor = user.free_lifecycle_at or user.plan_expires_at
        if anchor is None:
            anchor = now
        changed = user.free_lifecycle_at is None
        if changed:
            user.free_lifecycle_at = anchor
            await session.commit()
        if changed:
            from app.cache.subscription_cache import invalidate_all_subscription_caches
            await invalidate_all_subscription_caches()
        return anchor


async def claim_free_teaser(user_id: int, message_hash: str, now: datetime | None = None) -> tuple[bool, int]:
    """Atomically claim one of two teaser slots on lifecycle days 0/3/7/14."""
    now = now or datetime.now(timezone.utc)
    anchor = await ensure_free_lifecycle(user_id, now)
    if anchor is None:
        return False, -1
    day = lifecycle_day(anchor, now)
    redis = await get_redis()
    seen = await redis.set(f"lifecycle:seen:{user_id}:{message_hash}", "1", nx=True, ex=45 * 86400)
    if not seen or day not in TEASER_DAYS:
        return False, day
    key = f"lifecycle:teasers:{user_id}:{now.strftime('%Y-%m-%d')}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3 * 86400)
    return count <= TEASERS_PER_DAY, day


async def increment_lifecycle_matches(user_id: int) -> int:
    """Count all Free matches; analytics storage never blocks lead matching."""
    try:
        redis = await get_redis()
        key = f"lifecycle:matched:{user_id}"
        value = await redis.incr(key)
        await redis.expire(key, 45 * 86400)
        return int(value)
    except Exception:
        return 0


async def total_lifecycle_matches(user_id: int) -> int:
    try:
        redis = await get_redis()
        return int(await redis.get(f"lifecycle:matched:{user_id}") or 0)
    except Exception:
        return 0


async def daily_counts(user_id: int, date_str: str) -> tuple[int, int]:
    """Return (matched, delivered) counters; reporting failures degrade to zero."""
    try:
        redis = await get_redis()
        base = f"stats:daily:{user_id}:{date_str}"
        matched, sent = await redis.mget(f"{base}:matched", f"{base}:sent")
        return int(matched or 0), int(sent or 0)
    except Exception:
        return 0, 0

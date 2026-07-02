"""Redis-based subscription cache for fast user lookup."""

import json
import logging

from redis.asyncio import Redis
from sqlalchemy import select

from app.cache import get_redis
from app.db.session import async_session_factory
from app.db.models import UserSubscription, User, Segment

logger = logging.getLogger(__name__)

# ── Cache key patterns ──

CACHE_CHAT_KEY = "sub:by_chat:{chat_username}"
QUEUE_NOTIFICATIONS = "queue:notifications"
QUEUE_DEAD_LETTER = "dlq:notifications"
HEARTBEAT_KEY = "heartbeat:userbot:1"
LIMIT_REACHED_KEY = "limit_reached:{user_id}:{date}"
STATS_DAILY_KEY = "stats:daily:{user_id}:{date}"
CLASS_CACHE_KEY = "class:cache:{message_hash}"


# ── Build / rebuild cache ──

async def rebuild_subscription_cache(chat_username: str) -> None:
    """Rebuild the subscription cache for a given chat username.
    
    Maps chat → list of interested users with their segments, keywords, and geo filters.
    """
    redis = await get_redis()
    key = CACHE_CHAT_KEY.format(chat_username=chat_username)

    async with async_session_factory() as session:
        # Look up channel's country and city
        from app.db.models import CatalogChannel
        ch_result = await session.execute(
            select(CatalogChannel).where(CatalogChannel.chat_username == chat_username)
        )
        channel = ch_result.scalar_one_or_none()
        channel_country_id = channel.auto_matched_country_id if channel else None
        channel_city_id = channel.auto_matched_city_id if channel else None

        # Get all users with their subscriptions and keywords
        from app.db.models import User, UserSubscription, Keyword, SubscriptionCity
        users = (await session.execute(select(User))).scalars().all()

        cache_data: list[dict] = []
        for user in users:
            subs = (await session.execute(
                select(UserSubscription).where(UserSubscription.user_id == user.id)
            )).scalars().all()

            kws = (await session.execute(
                select(Keyword).where(Keyword.user_id == user.id, Keyword.is_active == True)
            )).scalars().all()

            # For each subscription, get subscription cities
            sub_geo = []  # list of {segment_id, country_id, city_ids}
            for sub in subs:
                city_ids = []
                if sub.mode == "cities":
                    sc_result = await session.execute(
                        select(SubscriptionCity.city_id).where(
                            SubscriptionCity.subscription_id == sub.id
                        )
                    )
                    city_ids = [row[0] for row in sc_result.all()]
                sub_geo.append({
                    "segment_id": sub.segment_id,
                    "country_id": sub.country_id,
                    "city_ids": city_ids,
                })

            cache_data.append({
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "lang": user.language,
                "plan": user.plan,
                "subscriptions": sub_geo,
                "keyword_texts": [kw.text for kw in kws],
            })

    await redis.set(key, json.dumps(cache_data, default=str))
    await redis.expire(key, 3600)
    logger.info("Rebuilt cache for @%s: %d users (country=%s)",
                chat_username, len(cache_data), channel_country_id)
    await redis.aclose()


async def get_interested_users(chat_username: str) -> list[dict]:
    """Get cached list of users interested in a given chat."""
    redis = await get_redis()
    key = CACHE_CHAT_KEY.format(chat_username=chat_username)
    data = await redis.get(key)
    await redis.aclose()

    if data:
        return json.loads(data)
    return []


# ── Queue operations ──

async def push_notification(payload: dict) -> None:
    """Push a notification to the Redis queue."""
    redis = await get_redis()
    await redis.lpush(QUEUE_NOTIFICATIONS, json.dumps(payload, default=str))
    await redis.aclose()


async def pop_notification(timeout: int = 5) -> dict | None:
    """Pop a notification from the queue (blocking)."""
    redis = await get_redis()
    result = await redis.brpop(QUEUE_NOTIFICATIONS, timeout=timeout)
    await redis.aclose()

    if result:
        _, data = result
        return json.loads(data)
    return None


# ── Deduplication ──

import hashlib


def build_message_hash(chat_username: str, message_id: int) -> str:
    """Build a deduplication hash for a message."""
    raw = f"{chat_username}:{message_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def is_duplicate(user_id: int, message_hash: str) -> bool:
    """Check if this notification was already sent to this user."""
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.db.models import SentLog

    async with async_session_factory() as session:
        result = await session.execute(
            select(SentLog).where(
                SentLog.user_id == user_id,
                SentLog.message_hash == message_hash,
            )
        )
        return result.scalar_one_or_none() is not None


async def mark_sent(user_id: int, message_hash: str, is_urgent: bool = False) -> None:
    """Mark a notification as sent."""
    from app.db.models import SentLog

    async with async_session_factory() as session:
        log = SentLog(user_id=user_id, message_hash=message_hash, is_urgent=is_urgent)
        session.add(log)
        await session.commit()


# ── Stats ──

async def increment_daily_stats(user_id: int, date_str: str, field: str) -> int:
    """Increment daily stats counter. Returns new value."""
    redis = await get_redis()
    key = STATS_DAILY_KEY.format(user_id=user_id, date=date_str)
    if field == "sent":
        key += ":sent"
    else:
        key += ":matched"
    value = await redis.incr(key)
    await redis.expireat(key, await _midnight_timestamp())
    await redis.aclose()
    return value


async def check_daily_limit(user_id: int, date_str: str, max_per_day: int) -> bool:
    """Check if user has exceeded daily notification limit. Returns True if limit reached."""
    redis = await get_redis()
    key = STATS_DAILY_KEY.format(user_id=user_id, date=date_str) + ":sent"
    count = int(await redis.get(key) or 0)
    await redis.aclose()
    return count >= max_per_day


async def _midnight_timestamp() -> int:
    """Get Unix timestamp for next midnight."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())

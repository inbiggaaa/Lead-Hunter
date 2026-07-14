"""Redis-based subscription cache for fast user lookup."""

import json
import logging

from redis.asyncio import Redis
from sqlalchemy import select

from app.cache import get_redis
from app.db.session import async_session_factory
from app.db.models import UserSubscription, User

logger = logging.getLogger(__name__)

# ── Cache key patterns ──

CACHE_CHAT_KEY = "sub:by_chat:{chat_username}"
QUEUE_NOTIFICATIONS = "queue:notifications"
QUEUE_DEAD_LETTER = "dlq:notifications"
HEARTBEAT_KEY = "heartbeat:userbot:1"
STATS_DAILY_KEY = "stats:daily:{user_id}:{date}"
CLASS_CACHE_KEY = "class:cache:{message_hash}"


# ── Build / rebuild cache ──

async def rebuild_subscription_cache(chat_username: str) -> None:
    """Rebuild the subscription cache for a given chat username.

    Maps chat → list of interested users with their segments, keywords, and
    geo filters. C5: four flat SELECTs joined in memory instead of 3 queries
    per user (N+1); users without a single subscription or keyword are not
    cached — they can never receive a notification.
    """
    redis = await get_redis()
    key = CACHE_CHAT_KEY.format(chat_username=chat_username)

    from app.db.models import Keyword, SubscriptionCity

    async with async_session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        subs = (await session.execute(select(UserSubscription))).scalars().all()
        kws = (await session.execute(
            select(Keyword).where(Keyword.is_active == True)
        )).scalars().all()
        sc_rows = (await session.execute(
            select(SubscriptionCity.subscription_id, SubscriptionCity.city_id)
        )).all()

    cities_by_sub: dict[int, list[int]] = {}
    for sub_id, city_id in sc_rows:
        cities_by_sub.setdefault(sub_id, []).append(city_id)
    subs_by_user: dict[int, list[UserSubscription]] = {}
    for sub in subs:
        subs_by_user.setdefault(sub.user_id, []).append(sub)
    kws_by_user: dict[int, list[str]] = {}
    for kw in kws:
        kws_by_user.setdefault(kw.user_id, []).append(kw.text)

    cache_data: list[dict] = []
    for user in users:
        user_subs = subs_by_user.get(user.id, [])
        keyword_texts = kws_by_user.get(user.id, [])
        if not user_subs and not keyword_texts:
            continue
        sub_geo = [
            {
                "segment_id": sub.segment_id,
                "country_id": sub.country_id,
                "city_ids": (
                    cities_by_sub.get(sub.id, []) if sub.mode == "cities" else []
                ),
            }
            for sub in user_subs
        ]
        cache_data.append({
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "lang": user.language,
            "plan": user.plan,
            "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
            "digest_mode": getattr(user, "digest_mode", "instant"),
            "free_lifecycle_at": user.free_lifecycle_at.isoformat() if user.free_lifecycle_at else None,
            "subscriptions": sub_geo,
            "keyword_texts": keyword_texts,
        })

    await redis.set(key, json.dumps(cache_data, default=str))
    await redis.expire(key, 3600)
    logger.info("Rebuilt cache for @%s: %d users with subs/keywords",
                chat_username, len(cache_data))


async def invalidate_all_subscription_caches() -> None:
    """Drop every sub:by_chat:* key.

    Call after COMMIT of any change to subscriptions, keywords, watched
    chats or user plan/blocked status. The cache content is identical for
    all chats (full user list), so per-chat invalidation is pointless —
    drop everything, lazy rebuild in _dispatch repopulates on next match.
    Without this, changes took up to 1h (TTL) to reach the poller.
    """
    redis = await get_redis()
    # Collect first, delete after: removing keys mid-SCAN skews the iteration.
    cursor = 0
    keys: list[str] = []
    while True:
        cursor, page = await redis.scan(
            cursor, match=CACHE_CHAT_KEY.format(chat_username="*"), count=200,
        )
        keys.extend(page)
        if cursor == 0:
            break
    deleted = await redis.delete(*keys) if keys else 0
    logger.info("Subscription cache invalidated: %d keys dropped", deleted)


async def get_interested_users(chat_username: str) -> list[dict]:
    """Get cached list of users interested in a given chat."""
    redis = await get_redis()
    key = CACHE_CHAT_KEY.format(chat_username=chat_username)
    data = await redis.get(key)

    if data:
        return json.loads(data)
    return []


# ── Queue operations ──

async def push_notification(payload: dict) -> None:
    """Push a notification to the Redis queue."""
    redis = await get_redis()
    await redis.lpush(QUEUE_NOTIFICATIONS, json.dumps(payload, default=str))


async def pop_notification(timeout: int = 5) -> dict | None:
    """Pop a notification from the queue (blocking)."""
    redis = await get_redis()
    result = await redis.brpop(QUEUE_NOTIFICATIONS, timeout=timeout)

    if result:
        _, data = result
        return json.loads(data)
    return None


# ── Deduplication ──

import hashlib


def build_message_hash(chat_username: str, message_id: int) -> str:
    """Build a deduplication hash for a message (by identity)."""
    raw = f"{chat_username}:{message_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_content_hash(chat_username: str, message_text: str) -> str:
    """Build a content-based dedup hash — same text → same hash.

    Normalizes whitespace, lowercases, truncates to 500 chars.
    Used with a 24h time window to suppress reposts while allowing
    legitimate re-posts after a day.
    """
    normalized = " ".join((message_text or "")[:500].lower().split())
    raw = f"{chat_username}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def is_duplicate(user_id: int, message_hash: str) -> bool:
    """Check if this notification was already sent to this user (by message identity)."""
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


async def is_content_duplicate(user_id: int, content_hash: str) -> bool:
    """Check if same content was sent to this user within the last 24 hours.

    Suppresses reposts of identical text while allowing legitimate
    re-posts after a day.
    """
    from datetime import datetime, timedelta, timezone
    from app.db.session import async_session_factory
    from sqlalchemy import select
    from app.db.models import SentLog

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with async_session_factory() as session:
        result = await session.execute(
            select(SentLog).where(
                SentLog.user_id == user_id,
                SentLog.content_hash == content_hash,
                SentLog.sent_at >= cutoff,
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def mark_sent(user_id: int, message_hash: str, is_urgent: bool = False,
                    content_hash: str | None = None, meta: dict | None = None) -> None:
    """Mark a notification as sent. Uses ON CONFLICT to avoid IntegrityError.
    `meta` (T5.2): {chat_username, sender, segment, message_id} для CSV-экспорта."""
    from app.db.models import SentLog
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    meta = meta or {}
    async with async_session_factory() as session:
        stmt = pg_insert(SentLog).values(
            user_id=user_id, message_hash=message_hash,
            is_urgent=is_urgent, content_hash=content_hash,
            chat_username=meta.get("chat_username"), sender=meta.get("sender"),
            segment=meta.get("segment"), message_id=meta.get("message_id"),
        ).on_conflict_do_nothing(index_elements=["user_id", "message_hash"])
        await session.execute(stmt)
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
    return value


async def record_paywall(trigger: str) -> None:
    """T6.4: счётчик показов пейволла по триггеру за день (мониторинг конверсии). TTL 40д.
    Fail-safe: аналитика НЕ должна ломать показ пейволла, если Redis недоступен."""
    from datetime import datetime, timezone
    try:
        redis = await get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"stats:paywall:{trigger}:{today}"
        await redis.incr(key)
        await redis.expire(key, 40 * 86400)
    except Exception:
        logger.debug("record_paywall skipped (redis unavailable)")


DIGEST_KEY = "digest:{user_id}"  # T5.3: буфер отложенных уведомлений


async def buffer_digest(user_id: int, payload: dict) -> None:
    """T5.3: отложить уведомление в буфер digest-пользователя (flush по расписанию)."""
    redis = await get_redis()
    key = DIGEST_KEY.format(user_id=user_id)
    await redis.rpush(key, json.dumps(payload, default=str))
    await redis.expire(key, 2 * 86400)  # страховка от зависших буферов


async def pop_all_digest(user_id: int) -> list[dict]:
    """T5.3: забрать и очистить весь буфер digest-пользователя."""
    redis = await get_redis()
    key = DIGEST_KEY.format(user_id=user_id)
    items = await redis.lrange(key, 0, -1)
    if items:
        await redis.delete(key)
    return [json.loads(i) for i in items]


SEG_STAT_KEY = "stats:seg:{user_id}:{date}:{segment_id}"
SEG_STAT_TTL_DAYS = 35  # T5.1: по-сегментная статистика для экрана «30 дней»


async def increment_segment_stat(user_id: int, date_str: str, segment_id: int) -> None:
    """T5.1: +1 к заявкам пользователя по сегменту за день. TTL 35 дней (персистентно,
    в отличие от matched/sent, которые гаснут в полночь)."""
    from datetime import datetime, timedelta, timezone
    redis = await get_redis()
    key = SEG_STAT_KEY.format(user_id=user_id, date=date_str, segment_id=segment_id)
    await redis.incr(key)
    await redis.expire(key, SEG_STAT_TTL_DAYS * 86400)


async def get_segment_stats(user_id: int, segment_ids: list[int], days: int) -> dict[int, int]:
    """Сумма заявок по каждому сегменту за последние `days` дней (T5.1)."""
    from datetime import datetime, timedelta, timezone
    if not segment_ids:
        return {}
    redis = await get_redis()
    today = datetime.now(timezone.utc).date()
    dates = [(today - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days)]
    totals: dict[int, int] = {}
    for sid in segment_ids:
        keys = [SEG_STAT_KEY.format(user_id=user_id, date=dt, segment_id=sid) for dt in dates]
        vals = await redis.mget(keys)
        totals[sid] = sum(int(v) for v in vals if v)
    return totals


async def _midnight_timestamp() -> int:
    """Get Unix timestamp for next midnight."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())

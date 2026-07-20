"""Redis-based subscription cache for fast user lookup."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.cache import get_redis
from app.db.session import async_session_factory
from app.db.models import UserSubscription, User

logger = logging.getLogger(__name__)

# ── Cache key patterns ──

CACHE_CHAT_KEY = "sub:by_chat:{chat_username}"
CACHE_SNAPSHOT_KEY = "sub:snapshot:v1"
QUEUE_NOTIFICATIONS = "queue:notifications"
QUEUE_PROCESSING = "queue:notifications:processing"
QUEUE_DEAD_LETTER = "dlq:notifications"
CLAIM_TTL_SEC = 300
MAX_DELIVERY_ATTEMPTS = 5
HEARTBEAT_KEY = "heartbeat:userbot:1"
STATS_DAILY_KEY = "stats:daily:{user_id}:{date}"
STATS_REDELIVERY = "stats:queue:redelivery_after_success"

_rebuild_lock = asyncio.Lock()


def user_is_deliverable(user: User, *, now: datetime | None = None) -> bool:
    """True when the user may receive leads / bot interactions."""
    if user.is_banned or user.is_blocked_bot:
        return False
    if not user.is_suspended:
        return True
    now = now or datetime.now(timezone.utc)
    # Suspended forever when suspended_until is NULL; otherwise until expiry.
    return bool(user.suspended_until and user.suspended_until <= now)


# ── Build / rebuild cache ──

async def _build_cache_payload() -> list[dict]:
    """Load deliverable users with subscriptions/keywords into one snapshot."""
    from app.db.models import Keyword, SubscriptionCity

    now = datetime.now(timezone.utc)
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
        if not user_is_deliverable(user, now=now):
            continue
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
    return cache_data


async def rebuild_subscription_cache(chat_username: str) -> None:
    """Rebuild shared snapshot and mirror it to the per-chat key.

    Content is identical for every chat; single-flight lock prevents stampedes
    after invalidate_all_subscription_caches().
    """
    async with _rebuild_lock:
        redis = await get_redis()
        existing = await redis.get(CACHE_SNAPSHOT_KEY)
        if existing:
            payload = existing
        else:
            cache_data = await _build_cache_payload()
            payload = json.dumps(cache_data, default=str)
            await redis.set(CACHE_SNAPSHOT_KEY, payload)
            await redis.expire(CACHE_SNAPSHOT_KEY, 3600)
            logger.info(
                "Rebuilt subscription snapshot: %d deliverable users",
                len(cache_data),
            )
        key = CACHE_CHAT_KEY.format(chat_username=chat_username)
        await redis.set(key, payload)
        await redis.expire(key, 3600)


async def invalidate_all_subscription_caches() -> None:
    """Drop every sub:by_chat:* key and the shared snapshot.

    Call after COMMIT of any change to subscriptions, keywords, watched
    chats or user plan/blocked status. The cache content is identical for
    all chats (full user list), so per-chat invalidation is pointless —
    drop everything, lazy rebuild in _dispatch repopulates on next match.
    Without this, changes took up to 1h (TTL) to reach the poller.
    """
    redis = await get_redis()
    # Collect first, delete after: removing keys mid-SCAN skews the iteration.
    cursor = 0
    keys: list[str] = [CACHE_SNAPSHOT_KEY]
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


# ── Queue operations (BLMOVE claim / ack / reclaim) ──

def _wrap_envelope(payload: dict, *, attempts: int = 0) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "claimed_at": None,
        "attempts": attempts,
        "body": payload,
    }


def _normalize_envelope(raw: dict | list) -> dict:
    """Accept wrapped envelopes and legacy bare payloads from the main queue."""
    if isinstance(raw, dict) and "body" in raw and "attempts" in raw:
        return {
            "id": raw.get("id") or str(uuid.uuid4()),
            "claimed_at": raw.get("claimed_at"),
            "attempts": int(raw.get("attempts") or 0),
            "body": raw["body"],
        }
    return _wrap_envelope(raw if isinstance(raw, dict) else {"_raw": raw})


def _serialize_envelope(envelope: dict) -> str:
    return json.dumps(envelope, default=str)


def _envelope_is_stale(envelope: dict, *, now: datetime | None = None) -> bool:
    claimed_at = envelope.get("claimed_at")
    if not claimed_at:
        return True
    now = now or datetime.now(timezone.utc)
    try:
        claimed = datetime.fromisoformat(claimed_at)
        if claimed.tzinfo is None:
            claimed = claimed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return (now - claimed).total_seconds() >= CLAIM_TTL_SEC


async def push_notification(payload: dict) -> None:
    """Push a notification envelope to the Redis queue (LPUSH / FIFO via RIGHT claim)."""
    redis = await get_redis()
    await redis.lpush(QUEUE_NOTIFICATIONS, _serialize_envelope(_wrap_envelope(payload)))


async def claim_notification(timeout: int = 5) -> dict | None:
    """Move one item main → processing and stamp claimed_at without a delete gap.

    BLMOVE places the item at processing index 0; LSET stamps it in place so a
    crash cannot drop the envelope between LREM and LPUSH.
    """
    redis = await get_redis()
    raw = await redis.blmove(
        QUEUE_NOTIFICATIONS, QUEUE_PROCESSING, timeout, "RIGHT", "LEFT",
    )
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    envelope = _normalize_envelope(json.loads(raw))
    envelope["claimed_at"] = datetime.now(timezone.utc).isoformat()
    await redis.lset(QUEUE_PROCESSING, 0, _serialize_envelope(envelope))
    return envelope


async def touch_claim(envelope: dict) -> dict:
    """Refresh claimed_at while a long TelegramRetryAfter sleep is in progress."""
    redis = await get_redis()
    envelope = dict(envelope)
    envelope["claimed_at"] = datetime.now(timezone.utc).isoformat()
    serialized = _serialize_envelope(envelope)
    items = await redis.lrange(QUEUE_PROCESSING, 0, -1)
    target_id = envelope.get("id")
    for idx, raw in enumerate(items):
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            current = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if current.get("id") == target_id:
            await redis.lset(QUEUE_PROCESSING, idx, serialized)
            break
    return envelope


async def ack_notification(envelope: dict) -> None:
    """Remove a successfully handled envelope from the processing list."""
    redis = await get_redis()
    await redis.lrem(QUEUE_PROCESSING, 1, _serialize_envelope(envelope))


async def fail_notification(envelope: dict, *, to_dlq: bool = False) -> None:
    """Drop from processing; requeue or dead-letter the body."""
    redis = await get_redis()
    serialized = _serialize_envelope(envelope)
    await redis.lrem(QUEUE_PROCESSING, 1, serialized)
    attempts = int(envelope.get("attempts") or 0) + 1
    body = envelope.get("body") or {}
    if to_dlq or attempts >= MAX_DELIVERY_ATTEMPTS:
        await redis.lpush(QUEUE_DEAD_LETTER, json.dumps(body, default=str))
        logger.error(
            "Notification dead-lettered after %d attempts (user=%s)",
            attempts, body.get("user_id"),
        )
        return
    retry = _wrap_envelope(body, attempts=attempts)
    await redis.lpush(QUEUE_NOTIFICATIONS, _serialize_envelope(retry))


async def reclaim_stale_notifications() -> int:
    """Move processing items older than CLAIM_TTL back to the main queue."""
    redis = await get_redis()
    items = await redis.lrange(QUEUE_PROCESSING, 0, -1)
    if not items:
        return 0
    now = datetime.now(timezone.utc)
    reclaimed = 0
    for raw in items:
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            envelope = _normalize_envelope(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            await redis.lrem(QUEUE_PROCESSING, 1, raw)
            await redis.lpush(QUEUE_DEAD_LETTER, raw if isinstance(raw, str) else raw.decode())
            continue
        if not _envelope_is_stale(envelope, now=now):
            continue
        removed = await redis.lrem(QUEUE_PROCESSING, 1, raw)
        if not removed:
            continue
        body = envelope.get("body") or {}
        attempts = int(envelope.get("attempts") or 0)
        await redis.lpush(
            QUEUE_NOTIFICATIONS,
            _serialize_envelope(_wrap_envelope(body, attempts=attempts)),
        )
        await redis.incr(STATS_REDELIVERY)
        reclaimed += 1
    if reclaimed:
        logger.warning("Reclaimed %d stale notification(s) from processing", reclaimed)
    return reclaimed


async def pop_notification(timeout: int = 5) -> dict | None:
    """Backward-compatible claim that returns the bare payload body."""
    envelope = await claim_notification(timeout=timeout)
    if envelope is None:
        return None
    return envelope.get("body")


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
DIGEST_PROCESSING_KEY = "digest:processing:{user_id}"
DIGEST_INFLIGHT_KEY = "digest:inflight:{user_id}"
DIGEST_TTL_SEC = 2 * 86400
DIGEST_CLAIM_TTL_SEC = CLAIM_TTL_SEC


async def buffer_digest(user_id: int, payload: dict) -> None:
    """T5.3: отложить уведомление в буфер (без mark_sent — только после flush)."""
    redis = await get_redis()
    key = DIGEST_KEY.format(user_id=user_id)
    inflight = DIGEST_INFLIGHT_KEY.format(user_id=user_id)
    message_hash = payload.get("message_hash")
    await redis.rpush(key, json.dumps(payload, default=str))
    await redis.expire(key, DIGEST_TTL_SEC)
    if message_hash:
        await redis.sadd(inflight, message_hash)
        await redis.expire(inflight, DIGEST_TTL_SEC)


async def is_digest_inflight(user_id: int, message_hash: str) -> bool:
    """True if this hash is buffered for digest and not yet delivered."""
    if not message_hash:
        return False
    redis = await get_redis()
    return bool(await redis.sismember(
        DIGEST_INFLIGHT_KEY.format(user_id=user_id), message_hash,
    ))


async def clear_digest_inflight(user_id: int, message_hash: str) -> None:
    redis = await get_redis()
    await redis.srem(DIGEST_INFLIGHT_KEY.format(user_id=user_id), message_hash)


async def claim_digest(user_id: int) -> list[dict]:
    """Atomically rename digest buffer → processing and return items."""
    redis = await get_redis()
    key = DIGEST_KEY.format(user_id=user_id)
    proc = DIGEST_PROCESSING_KEY.format(user_id=user_id)
    if not await redis.exists(key):
        return []
    try:
        await redis.rename(key, proc)
    except Exception:
        # Race: key vanished between EXISTS and RENAME
        return []
    await redis.expire(proc, DIGEST_CLAIM_TTL_SEC)
    items = await redis.lrange(proc, 0, -1)
    return [json.loads(i) for i in items]


async def ack_digest_head(user_id: int, message_hash: str | None) -> None:
    """LPOP one delivered item from digest processing (FIFO with claim order)."""
    redis = await get_redis()
    proc = DIGEST_PROCESSING_KEY.format(user_id=user_id)
    await redis.lpop(proc)
    if message_hash:
        await redis.srem(DIGEST_INFLIGHT_KEY.format(user_id=user_id), message_hash)
    if await redis.llen(proc) == 0:
        await redis.delete(proc)


async def finish_digest_claim(user_id: int) -> None:
    """Drop empty/finished digest processing key."""
    redis = await get_redis()
    await redis.delete(DIGEST_PROCESSING_KEY.format(user_id=user_id))


async def restore_digest(user_id: int, remaining: list[dict]) -> None:
    """Put undelivered digest items back into the live buffer."""
    redis = await get_redis()
    proc = DIGEST_PROCESSING_KEY.format(user_id=user_id)
    key = DIGEST_KEY.format(user_id=user_id)
    await redis.delete(proc)
    if not remaining:
        return
    await redis.rpush(key, *[json.dumps(p, default=str) for p in remaining])
    await redis.expire(key, DIGEST_TTL_SEC)


async def reclaim_stale_digests(user_ids: list[int]) -> int:
    """Rename stale digest:processing keys back to digest:{uid}."""
    redis = await get_redis()
    reclaimed = 0
    for uid in user_ids:
        proc = DIGEST_PROCESSING_KEY.format(user_id=uid)
        key = DIGEST_KEY.format(user_id=uid)
        ttl = await redis.ttl(proc)
        # Missing key → -2; no expire → -1. Reclaim when TTL nearly exhausted
        # or key exists without a live buffer (crash mid-flush).
        if ttl == -2:
            continue
        if ttl > 0 and ttl > DIGEST_CLAIM_TTL_SEC // 2:
            continue
        if not await redis.exists(proc):
            continue
        if await redis.exists(key):
            # Merge processing back into live buffer
            items = await redis.lrange(proc, 0, -1)
            if items:
                await redis.rpush(key, *items)
            await redis.delete(proc)
        else:
            try:
                await redis.rename(proc, key)
            except Exception:
                continue
        reclaimed += 1
    return reclaimed


async def pop_all_digest(user_id: int) -> list[dict]:
    """Backward-compatible: claim digest buffer (now via RENAME, not DELETE)."""
    return await claim_digest(user_id)


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

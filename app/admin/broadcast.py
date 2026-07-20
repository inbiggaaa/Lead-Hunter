"""Broadcast page — select users and send bulk messages."""

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select

from app.cache import get_redis
from app.db.models import User
from app.db.session import async_session_factory
from app.config import settings

logger = logging.getLogger(__name__)

BROADCAST_LOCK_KEY = "admin:broadcast:lock"
BROADCAST_CONFIRM_PREFIX = "admin:broadcast:confirm:"
BROADCAST_CONFIRM_TTL = 300
BROADCAST_LOCK_TTL = 3600


def _normalize_filter(value: str | None) -> str:
    return value.strip() if value and value.strip() else "all"


def _recipient_query(plan_filter: str, source_filter: str):
    """Build one recipient selection shared by preview and send."""
    now = datetime.now(UTC)
    stmt = select(User.telegram_id, User.id).where(
        User.is_banned.is_(False),
        User.is_blocked_bot.is_(False),
        ~and_(
            User.is_suspended.is_(True),
            or_(User.suspended_until.is_(None), User.suspended_until > now),
        ),
    )
    if plan_filter != "all":
        stmt = stmt.where(User.plan == plan_filter)
    if source_filter != "all":
        stmt = stmt.where(User.source == source_filter)
    return stmt


async def create_broadcast_preview(
    plan_filter: str | None,
    source_filter: str | None,
    text: str,
) -> dict[str, int | str]:
    """Count recipients and store a one-use confirmation bound to payload."""
    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("Broadcast text cannot be empty")
    plan = _normalize_filter(plan_filter)
    source = _normalize_filter(source_filter)
    async with async_session_factory() as session:
        total = len((await session.execute(_recipient_query(plan, source))).all())
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"plan": plan, "source": source, "text": normalized_text})
    redis = await get_redis()
    await redis.setex(f"{BROADCAST_CONFIRM_PREFIX}{token}", BROADCAST_CONFIRM_TTL, payload)
    return {"total": total, "confirmation_token": token}


async def _consume_confirmation(
    token: str, plan_filter: str | None, source_filter: str | None, text: str
) -> bool:
    redis = await get_redis()
    key = f"{BROADCAST_CONFIRM_PREFIX}{token}"
    payload = await redis.getdel(key)
    if not payload:
        return False
    expected = json.dumps(
        {
            "plan": _normalize_filter(plan_filter),
            "source": _normalize_filter(source_filter),
            "text": text.strip(),
        }
    )
    if isinstance(payload, bytes):
        payload = payload.decode()
    return secrets.compare_digest(payload, expected)


async def broadcast_send(
    plan_filter: str | None = None,
    source_filter: str | None = None,
    text: str = "",
    confirmation_token: str = "",
) -> dict:
    """Send one confirmed broadcast using a Redis distributed lock."""
    if not text.strip():
        return {"error": "Broadcast text cannot be empty"}
    if not confirmation_token or not await _consume_confirmation(
        confirmation_token, plan_filter, source_filter, text
    ):
        return {"error": "Invalid or expired confirmation token"}
    redis = await get_redis()
    lock_value = secrets.token_urlsafe(16)
    if not await redis.set(BROADCAST_LOCK_KEY, lock_value, nx=True, ex=BROADCAST_LOCK_TTL):
        return {"error": "Рассылка уже выполняется"}

    try:
        async with async_session_factory() as session:
            result = await session.execute(
                _recipient_query(_normalize_filter(plan_filter), _normalize_filter(source_filter))
            )
            users = result.all()

        sent = 0
        failed = 0
        from aiogram import Bot
        bot = Bot(token=settings.bot_token)

        for telegram_id, user_id in users:
            try:
                await bot.send_message(telegram_id, text)
                sent += 1
                await asyncio.sleep(1 / 30)  # RATE_SLEEP 1/30
            except Exception as e:
                logger.warning("Broadcast failed for user %d: %s", user_id, e)
                failed += 1

        await bot.session.close()
        return {"sent": sent, "failed": failed, "total": len(users)}
    finally:
        # Release only our lock — avoid deleting another process's lock.
        current = await redis.get(BROADCAST_LOCK_KEY)
        if isinstance(current, bytes):
            current = current.decode()
        if current == lock_value:
            await redis.delete(BROADCAST_LOCK_KEY)


async def get_broadcast_stats() -> dict:
    """Get user counts per plan and source for preview."""
    async with async_session_factory() as session:
        plan_result = await session.execute(select(User.plan, func.count(User.id)).group_by(User.plan))
        plans = {plan: count for plan, count in plan_result.all()}
        source_result = await session.execute(select(User.source, func.count(User.id)).group_by(User.source))
        sources = {src: count for src, count in source_result.all()}
        total = sum(plans.values())
    return {"total": total, "plans": plans, "sources": sources}

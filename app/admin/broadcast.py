"""Broadcast page — select users and send bulk messages."""

import asyncio
import logging

from sqlalchemy import func, select

from app.db.models import User
from app.db.session import async_session_factory
from app.config import settings

logger = logging.getLogger(__name__)

# Prevent double run
_broadcast_lock = asyncio.Lock()


async def broadcast_send(
    plan_filter: str | None = None,
    source_filter: str | None = None,
    text: str = "",
) -> dict:
    """Send broadcast message to filtered users. Returns stats."""
    if _broadcast_lock.locked():
        return {"error": "Рассылка уже выполняется"}

    async with _broadcast_lock:
        async with async_session_factory() as session:
            stmt = select(User.telegram_id, User.id)
            if plan_filter and plan_filter != "all":
                stmt = stmt.where(User.plan == plan_filter)
            if source_filter and source_filter != "all":
                stmt = stmt.where(User.source == source_filter)

            result = await session.execute(stmt)
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


async def get_broadcast_stats() -> dict:
    """Get user counts per plan and source for preview."""
    async with async_session_factory() as session:
        plan_result = await session.execute(select(User.plan, func.count(User.id)).group_by(User.plan))
        plans = {plan: count for plan, count in plan_result.all()}
        source_result = await session.execute(select(User.source, func.count(User.id)).group_by(User.source))
        sources = {src: count for src, count in source_result.all()}
        total = sum(plans.values())
    return {"total": total, "plans": plans, "sources": sources}

"""End-of-day report task for Free users."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select, func

from app.config import settings
from app.db.models import User, SentLog
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def send_end_of_day_reports():
    """Send daily report to Free users at configured hour."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    async with async_session_factory() as session:
        free_users = (await session.execute(
            select(User).where(User.plan == "free")
        )).scalars().all()

    bot = Bot(token=settings.bot_token)
    sent = 0

    for user in free_users:
        # Count today's notifications
        async with async_session_factory() as session:
            count = (await session.execute(
                select(func.count(SentLog.id)).where(
                    SentLog.user_id == user.id,
                    SentLog.sent_at >= today_str,
                )
            )).scalar() or 0

        max_n = settings.notifications_per_day_free
        text = (
            f"📊 Итоги дня\n\n"
            f"Уведомлений сегодня: {count}/{max_n}\n\n"
            f"💰 Перейди на Pro чтобы снять лимит и видеть контакты!"
        )

        try:
            await bot.send_message(user.telegram_id, text)
            sent += 1
        except Exception:
            continue

        await asyncio.sleep(0.1)

    await bot.session.close()
    logger.info("End-of-day reports sent to %d free users", sent)


async def end_of_day_loop():
    """Run end-of-day reports at the configured hour."""
    while True:
        now = datetime.now(timezone.utc)
        run_hour = settings.daily_report_hour  # default 19
        next_run = now.replace(hour=run_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run = next_run.replace(day=now.day + 1)
        wait = (next_run - now).total_seconds()

        logger.info("Next end-of-day report at %s", next_run)
        await asyncio.sleep(wait)

        try:
            await send_end_of_day_reports()
        except Exception:
            logger.exception("End-of-day report failed")

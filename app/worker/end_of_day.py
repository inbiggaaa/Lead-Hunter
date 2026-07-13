"""End-of-day report task for Free users."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, func

from app.config import settings
from app.db.models import User, SentLog
from app.db.session import async_session_factory
from app.locales import get_text

logger = logging.getLogger(__name__)


async def send_end_of_day_reports():
    """End-of-day отчёт Free (T4.2, #81): «скрытые контакты», без лимита.
    Только Free и только если сегодня были заявки (иначе не отправляем)."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    async with async_session_factory() as session:
        free_users = (await session.execute(
            select(User).where(User.plan == "free")
        )).scalars().all()

    bot = Bot(token=settings.bot_token)
    start_price = settings.price_start_monthly_usd
    sent = 0

    for user in free_users:
        async with async_session_factory() as session:
            count = (await session.execute(
                select(func.count(SentLog.id)).where(
                    SentLog.user_id == user.id,
                    SentLog.sent_at >= today_str,
                )
            )).scalar() or 0

        if count == 0:
            continue  # нет заявок — не беспокоим

        lang = user.language or "ru"
        text = get_text(lang, "eod_body", count=count)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=get_text(lang, "eod_btn", price=start_price), callback_data="menu:plan")]])

        try:
            await bot.send_message(user.telegram_id, text, reply_markup=kb, parse_mode="HTML")
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

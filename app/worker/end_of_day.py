"""Sparse end-of-day lifecycle reports for users without a subscription."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import settings
from app.db.models import User
from app.db.session import async_session_factory
from app.lifecycle import TEASER_DAYS, daily_counts, lifecycle_day
from app.locales import get_text, normalize_language

logger = logging.getLogger(__name__)


def _report_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_start", price=settings.price_start_monthly_usd), callback_data="pay_plan:start")],
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_pro", price=settings.price_pro_monthly_usd), callback_data="pay_plan:pro")],
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_business", price=settings.price_business_monthly_usd), callback_data="pay_plan:business")],
    ])


async def send_end_of_day_reports(now: datetime | None = None):
    """Report total niche demand and missed leads only on days 0/3/7/14."""
    now = now or datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    async with async_session_factory() as session:
        users = (await session.execute(
            select(User).where(User.plan == "free", User.free_lifecycle_at.isnot(None))
        )).scalars().all()

    bot = Bot(token=settings.bot_token)
    sent = 0
    try:
        for user in users:
            day = lifecycle_day(user.free_lifecycle_at, now)
            if day not in TEASER_DAYS:
                continue
            matched, delivered = await daily_counts(user.id, today_str)
            if matched <= 0:
                if day != 0:
                    continue
                lang = normalize_language(user.language)
                zero_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text(lang, "eod_zero_btn"), callback_data="menu:subs")]])
                try:
                    await bot.send_message(user.telegram_id, get_text(lang, "eod_zero"), reply_markup=zero_kb, parse_mode="HTML")
                    sent += 1
                except Exception:
                    logger.exception("Zero-lead diagnostic failed for user %d", user.id)
                continue
            missed = max(0, matched - delivered)
            lang = normalize_language(user.language)
            text = get_text(lang, "eod_body", total=matched, delivered=delivered, missed=missed)
            try:
                await bot.send_message(user.telegram_id, text, reply_markup=_report_keyboard(lang), parse_mode="HTML")
                sent += 1
                from app.analytics import record_event
                await record_event("lifecycle_report_sent", user, context={"lifecycle_day": day, "matched": matched, "delivered": delivered, "missed": missed})
            except Exception:
                logger.exception("EOD lifecycle report failed for user %d", user.id)
            await asyncio.sleep(0.1)
    finally:
        await bot.session.close()
    logger.info("End-of-day lifecycle reports sent to %d users", sent)


async def end_of_day_loop():
    while True:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=settings.daily_report_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await send_end_of_day_reports()
        except Exception:
            logger.exception("End-of-day report failed")

"""Subscription reminders and sparse no-subscription lifecycle scheduler."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import settings
from app.db.models import Reminder, User, WinbackOffer
from app.db.session import async_session_factory
from app.lifecycle import OFFER_DAY, OFFER_DISCOUNT, OFFER_HOURS, lifecycle_day
from app.locales import get_text, normalize_language

logger = logging.getLogger(__name__)


def _upgrade_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text(lang, "reminder_btn_plans", price=settings.price_start_monthly_usd),
        callback_data="menu:plan",
    )]])


def _reminder_kb(rtype: str, user_plan: str | None = None, lang: str = "ru"):
    if rtype == "trial_ending":
        return _upgrade_kb(lang)
    if rtype == "subscription_ending" and user_plan in ("start", "pro", "business"):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "reminder_btn_renew"), callback_data=f"pay_plan:{user_plan}")],
            [InlineKeyboardButton(text=get_text(lang, "reminder_btn_other_plans"), callback_data="menu:plan")],
        ])
    return None


async def _maybe_send(session, user: User, rtype: str, day: int, missed: int | None = None):
    existing = (await session.execute(select(Reminder).where(
        Reminder.user_id == user.id, Reminder.type == rtype, Reminder.day_number == day
    ))).scalar_one_or_none()
    if existing:
        return
    lang = normalize_language(user.language)
    try:
        message = get_text(lang, f"reminder_{rtype}_{day}", start=settings.price_start_monthly_usd, missed=missed or 0)
    except KeyError:
        return
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(user.telegram_id, message, reply_markup=_reminder_kb(rtype, getattr(user, "plan", None), lang))
    except Exception:
        logger.exception("Failed to send reminder to %d", user.telegram_id)
        return
    finally:
        await bot.session.close()
    session.add(Reminder(user_id=user.id, type=rtype, day_number=day))
    await session.commit()


def _discount_total(monthly: float) -> float:
    return monthly * 3 * (1 - OFFER_DISCOUNT)


def _offer_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "winback_btn_start", total=f"{_discount_total(settings.price_start_monthly_usd):.2f}"), callback_data="winback:buy:start")],
        [InlineKeyboardButton(text=get_text(lang, "winback_btn_pro", total=f"{_discount_total(settings.price_pro_monthly_usd):.2f}"), callback_data="winback:buy:pro")],
        [InlineKeyboardButton(text=get_text(lang, "winback_btn_business", total=f"{_discount_total(settings.price_business_monthly_usd):.2f}"), callback_data="winback:buy:business")],
    ])


def _expired_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Plan choice → straight to payment, shown when a paid plan expires."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_start", price=settings.price_start_monthly_usd), callback_data="pay_plan:start")],
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_pro", price=settings.price_pro_monthly_usd), callback_data="pay_plan:pro")],
        [InlineKeyboardButton(text=get_text(lang, "eod_btn_business", price=settings.price_business_monthly_usd), callback_data="pay_plan:business")],
    ])


async def _send_expiry_notice(user: User):
    """One-shot «subscription expired» notice with plan choice → payment.
    Fires once: the caller has already flipped the plan to free, so the daily
    sweep won't re-select the user."""
    lang = normalize_language(user.language)
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            user.telegram_id, get_text(lang, "reminder_subscription_expired"),
            reply_markup=_expired_keyboard(lang), parse_mode="HTML",
        )
    except Exception:
        logger.exception("Failed to send expiry notice to %d", user.telegram_id)
    finally:
        await bot.session.close()


async def _maybe_send_winback_offer(session, user: User, now: datetime):
    from app.lifecycle import is_lifecycle_marketing_disabled
    if await is_lifecycle_marketing_disabled(user.id):
        return
    offer = (await session.execute(select(WinbackOffer).where(WinbackOffer.user_id == user.id))).scalar_one_or_none()
    if offer:
        return
    expires = now + timedelta(hours=OFFER_HOURS)
    offer = WinbackOffer(user_id=user.id, offered_at=now, expires_at=expires)
    session.add(offer)
    await session.flush()
    from app.lifecycle import total_lifecycle_matches
    missed = await total_lifecycle_matches(user.id)
    lang = normalize_language(user.language)
    text = get_text(lang, "winback_offer", missed=missed, expires=expires.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"))
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(user.telegram_id, text, reply_markup=_offer_keyboard(lang), parse_mode="HTML")
    except Exception:
        await session.rollback()
        logger.exception("Failed to send winback offer to %d", user.telegram_id)
        return
    finally:
        await bot.session.close()
    session.add(Reminder(user_id=user.id, type="winback_offer", day_number=OFFER_DAY))
    await session.commit()
    from app.analytics import record_event
    await record_event("winback_offer_sent", user, context={"lifecycle_day": OFFER_DAY, "missed": missed, "discount": 25})


async def send_reminders(now: datetime | None = None):
    """Expire access exactly, send pre-expiry reminders, and issue day-30 offers."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    async with async_session_factory() as session:
        expiring = (await session.execute(select(User).where(
            User.plan.in_(["trial", "start", "pro", "business"]),
            User.plan_expires_at.isnot(None), User.plan_expires_at <= now,
        ))).scalars().all()
        newly_expired_paid = []
        for user in expiring:
            was_paid = user.plan in ("start", "pro", "business")
            user.plan = "free"
            user.free_lifecycle_at = user.plan_expires_at or now
            if was_paid:
                newly_expired_paid.append(user)
        if expiring:
            await session.commit()
            from app.cache.subscription_cache import invalidate_all_subscription_caches
            await invalidate_all_subscription_caches()
            # Explicit «subscription expired» notice (paid plans only); trial
            # expiry is covered by the Free lifecycle EOD flow.
            for user in newly_expired_paid:
                await _send_expiry_notice(user)

        active = (await session.execute(select(User).where(
            User.plan.in_(["trial", "start", "pro", "business"]), User.plan_expires_at > now
        ))).scalars().all()
        for user in active:
            days_until = (user.plan_expires_at.date() - today).days
            if user.plan == "trial" and days_until in (2, 1):
                await _maybe_send(session, user, "trial_ending", days_until)
            elif user.plan in ("start", "pro", "business") and days_until in (5, 2, 1):
                await _maybe_send(session, user, "subscription_ending", days_until)

        free_users = (await session.execute(select(User).where(
            User.plan == "free", User.free_lifecycle_at.isnot(None), User.is_blocked_bot == False
        ))).scalars().all()
        for user in free_users:
            if lifecycle_day(user.free_lifecycle_at, now) == OFFER_DAY:
                await _maybe_send_winback_offer(session, user, now)
    logger.info("Reminder check complete")


async def send_periodic_messages():
    """Legacy calendar broadcasts are disabled; lifecycle reports replace them."""
    return None


async def reminders_loop():
    while True:
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await send_reminders()
        except Exception:
            logger.exception("Reminder task failed")

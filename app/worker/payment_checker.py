"""Pending payment checker — polls CryptoBot invoices in background."""

import asyncio
import json
import logging

from app.cache import get_redis
from app.payments.cryptobot import CryptoBotPaymentProvider
from app.config import settings
from app.locales import get_text, normalize_language

logger = logging.getLogger(__name__)

PENDING_KEY = "pay:pending"  # Redis hash: invoice_id -> JSON {user_id, plan, period_key, chat_id}


async def add_pending(invoice_id: str, user_id: int, plan: str, period_key: str, chat_id: int):
    """Store a pending payment for background checking."""
    redis = await get_redis()
    await redis.hset(PENDING_KEY, invoice_id, json.dumps({
        "user_id": user_id, "plan": plan, "period_key": period_key, "chat_id": chat_id,
    }))
    logger.info("Pending payment added: %s for user %d", invoice_id, user_id)


async def remove_pending(invoice_id: str):
    """Remove a processed payment."""
    redis = await get_redis()
    await redis.hdel(PENDING_KEY, invoice_id)


async def check_pending_payments():
    """Check all pending invoices and activate paid ones."""
    redis = await get_redis()
    pending = await redis.hgetall(PENDING_KEY)

    if not pending:
        return

    provider = CryptoBotPaymentProvider()
    paid_count = 0

    for invoice_id, data_json in pending.items():
        try:
            data = json.loads(data_json)
            status = await provider.check_payment(invoice_id)
            if status == "paid":
                await _activate(data, invoice_id)
                await remove_pending(invoice_id)
                paid_count += 1
            elif status == "expired":
                await _notify_expired(data)
                await remove_pending(invoice_id)
                logger.info("Expired invoice removed: %s", invoice_id)
        except Exception:
            logger.exception("Failed to check invoice %s", invoice_id)

    if paid_count:
        logger.info("Activated %d paid invoices", paid_count)


async def _activate(data: dict, invoice_id: str):
    """Activate subscription and notify user."""
    import datetime
    from aiogram import Bot
    from app.db.session import async_session_factory
    from app.db.models import User, Subscription
    from sqlalchemy import select

    user_id = data["user_id"]
    plan = data["plan"]
    period_key = data["period_key"]
    chat_id = data["chat_id"]

    # Calculate info
    from app.bot.handlers.plan import _calc, plan_display_name, period_display_name
    info = _calc(plan, period_key)

    async with async_session_factory() as session:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not user:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30 * info["months"])

        session.add(Subscription(
            user_id=user.id, plan=plan, period=period_key, expires_at=expires,
            payment_method="cryptobot", payment_status="paid",
            invoice_id=invoice_id, amount=info["total"],
        ))
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        await session.commit()

    # Смена плана меняет формат уведомлений (Free скрывает контакты) — сбросить
    # кэш подписок сразу, иначе оплаченный пользователь до TTL (1ч) видел бы Free.
    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()

    # Apply referral bonus
    from app.bot.handlers.plan import _apply_referral_bonus
    await _apply_referral_bonus(user_id)

    # Notify admin
    from app.userbot.discovery import notify_new_subscription
    import asyncio as aio
    user_obj = await _get_user_for_notify(user_id)
    aio.create_task(notify_new_subscription(user_obj.username if user_obj else None, user_obj.telegram_id if user_obj else 0, plan, period_key, "direct", info["total"]))

    # Notify user in the persisted language.
    lang = normalize_language(getattr(user, "language", None))
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            chat_id,
            get_text(lang, "payment_success", plan=plan_display_name(plan, lang), period=period_display_name(period_key, lang), date=expires.strftime("%d.%m.%Y")),
        )
    except Exception:
        logger.exception("Failed to notify user %d", user_id)
    finally:
        await bot.session.close()

    # T4.5: годовой апселл на 2-м подряд месячном платеже
    from app.bot.handlers.plan import maybe_offer_annual
    await maybe_offer_annual(user_id, chat_id, plan, period_key)


async def _get_user_for_notify(user_id: int):
    from app.db.session import async_session_factory
    from app.db.models import User
    from sqlalchemy import select
    async with async_session_factory() as s:
        return (await s.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def _notify_expired(data: dict):
    """Уведомить пользователя об истёкшем крипто-инвойсе (T2.2) с кнопкой повтора."""
    from aiogram import Bot
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    from app.locales import get_text

    user = await _get_user_for_notify(data["user_id"])
    lang = user.language if user else "ru"
    plan, period_key = data["plan"], data["period_key"]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text(lang, "pay_err_retry"), callback_data=f"pay_period:{plan}:{period_key}")]])
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(data["chat_id"], get_text(lang, "pay_error_expired"),
                               reply_markup=kb, parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify expired invoice for user %s", data.get("user_id"))
    finally:
        await bot.session.close()


async def payment_checker_loop():
    """Background loop: check pending payments every 5 seconds."""
    while True:
        await check_pending_payments()
        await asyncio.sleep(5)

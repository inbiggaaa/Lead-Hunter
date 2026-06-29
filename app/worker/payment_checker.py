"""Pending payment checker — polls CryptoBot invoices in background."""

import asyncio
import json
import logging

from app.cache import get_redis
from app.payments.cryptobot import CryptoBotPaymentProvider
from app.config import settings

logger = logging.getLogger(__name__)

PENDING_KEY = "pay:pending"  # Redis hash: invoice_id -> JSON {user_id, plan, period_key, chat_id}


async def add_pending(invoice_id: str, user_id: int, plan: str, period_key: str, chat_id: int):
    """Store a pending payment for background checking."""
    redis = await get_redis()
    await redis.hset(PENDING_KEY, invoice_id, json.dumps({
        "user_id": user_id, "plan": plan, "period_key": period_key, "chat_id": chat_id,
    }))
    await redis.close()
    logger.info("Pending payment added: %s for user %d", invoice_id, user_id)


async def remove_pending(invoice_id: str):
    """Remove a processed payment."""
    redis = await get_redis()
    await redis.hdel(PENDING_KEY, invoice_id)
    await redis.close()


async def check_pending_payments():
    """Check all pending invoices and activate paid ones."""
    redis = await get_redis()
    pending = await redis.hgetall(PENDING_KEY)
    await redis.close()

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
    from app.bot.handlers.plan import _calc
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

    # Notify user
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(
            chat_id,
            f"✅ Оплата прошла!\n\n"
            f"Тариф: {info['plan_name']}\n"
            f"Срок: {info['period_label']}\n"
            f"Действует до: {expires.strftime('%d.%m.%Y')}",
        )
    except Exception:
        logger.exception("Failed to notify user %d", user_id)
    finally:
        await bot.session.close()


async def payment_checker_loop():
    """Background loop: check pending payments every 5 seconds."""
    while True:
        await check_pending_payments()
        await asyncio.sleep(5)

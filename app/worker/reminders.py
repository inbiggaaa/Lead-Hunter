"""Reminders and periodic messages scheduler."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from app.config import settings
from app.db.models import User, Reminder, PeriodicPref
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# ── Reminders ──

REMINDER_MESSAGES = {
    "trial_expired": {
        1: "⏰ Ваш пробный период закончился. Перейди на Pro или Business чтобы продолжить получать заявки! 💰",
        3: "👋 Прошло 3 дня с окончания триала. На Free-тарифе ты получаешь 10 уведомлений/день — апни до Pro чтобы снять лимит.",
        7: "📊 Неделя после триала. Как успехи? Напомню: на Pro ты получаешь полные контакты и 150 уведомлений/день.",
    },
    "subscription_expired": {
        1: "⏰ Твоя подписка истекла. Продли чтобы не терять заявки! 💰",
        3: "👋 3 дня без подписки. Заявки продолжают приходить, но с ограничениями Free.",
        7: "📊 Неделя без подписки. Самое время вернуться!",
    },
    "inactive": {
        14: "👋 Давно не виделись! За 2 недели появились новые заявки по твоим направлениям. Загляни!",
        28: "📊 Месяц без активности. Твои подписки всё ещё работают — может, настроим новые направления?",
    },
}


async def send_reminders():
    """Check and send scheduled reminders. Called daily."""
    today = datetime.now(timezone.utc).date()

    async with async_session_factory() as session:
        # Auto-downgrade expired trial users
        expired_trial = (await session.execute(
            select(User).where(
                User.plan == "trial",
                User.plan_expires_at.isnot(None),
                User.plan_expires_at < today,
            )
        )).scalars().all()

        for user in expired_trial:
            user.plan = "free"
            logger.info("Trial expired for user %d → downgraded to free", user.telegram_id)
        await session.commit()
        # Trial expired reminders
        trial_users = (await session.execute(
            select(User).where(
                User.plan == "trial",
                User.plan_expires_at.isnot(None),
            )
        )).scalars().all()

        for user in trial_users:
            days_since = (today - user.plan_expires_at.date()).days
            if days_since in (1, 3, 7):
                await _maybe_send(session, user, "trial_expired", days_since)

        # Subscription expired reminders
        expired_users = (await session.execute(
            select(User).where(
                User.plan.in_(["pro", "business"]),
                User.plan_expires_at.isnot(None),
                User.plan_expires_at < today,
            )
        )).scalars().all()

        for user in expired_users:
            days_since = (today - user.plan_expires_at.date()).days
            if days_since in (1, 3, 7):
                await _maybe_send(session, user, "subscription_expired", days_since)

        # Inactive reminders (users who haven't been active for 14+ days)
        inactive_users = (await session.execute(
            select(User).where(User.created_at < today - timedelta(days=14))
        )).scalars().all()

        for user in inactive_users:
            days_inactive = (today - user.created_at.date()).days
            # Only trigger at specific thresholds
            if days_inactive == 14:
                await _maybe_send(session, user, "inactive", 14)
            elif days_inactive == 28:
                await _maybe_send(session, user, "inactive", 28)

    logger.info("Reminder check complete")


async def _maybe_send(session, user: User, rtype: str, day: int):
    """Send reminder if not already sent and not disabled."""
    # Check if already sent
    result = await session.execute(
        select(Reminder).where(
            Reminder.user_id == user.id,
            Reminder.type == rtype,
            Reminder.day_number == day,
        )
    )
    existing = result.scalar_one_or_none()
    if existing and existing.is_disabled:
        return
    if existing:
        return  # Already sent

    message = REMINDER_MESSAGES.get(rtype, {}).get(day)
    if not message:
        return

    # Send via Bot API
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(user.telegram_id, message)
    except Exception:
        logger.exception("Failed to send reminder to %d", user.telegram_id)
        return
    finally:
        await bot.session.close()

    # Record
    reminder = Reminder(user_id=user.id, type=rtype, day_number=day)
    session.add(reminder)
    await session.commit()
    logger.info("Sent reminder '%s' day %d to user %d", rtype, day, user.id)


# ── Periodic messages for Free users ──

PERIODIC_MESSAGES = {
    "weekly_digest": "📊 Итоги недели: ты получил заявки по твоим направлениям. Проверь главное меню чтобы посмотреть!",
    "niche_growth": "🌱 Новое в нише: мы добавили свежие каналы в твоих направлениях. Загляни в каталог!",
    "monthly_summary": "📈 Твой месяц: статистика заявок и новые возможности. Открой бота чтобы увидеть!",
}


async def send_periodic_messages():
    """Send periodic Free-tier messages based on day of week/month."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon
    day_of_month = now.day

    # Weekly digest: Monday
    if weekday == 0:
        await _send_periodic("weekly_digest")

    # Niche growth: Thursday, every 2 weeks
    if weekday == 3 and (day_of_month % 14 < 7):
        await _send_periodic("niche_growth")

    # Monthly summary: 1st of month
    if day_of_month == 1:
        await _send_periodic("monthly_summary")


async def _send_periodic(msg_type: str):
    """Send a periodic message to all eligible Free users."""
    message = PERIODIC_MESSAGES.get(msg_type)
    if not message:
        return

    bot = Bot(token=settings.bot_token)

    async with async_session_factory() as session:
        users = (await session.execute(
            select(User).where(User.plan == "free")
        )).scalars().all()

        for user in users:
            # Check if user has disabled this type
            pref_result = await session.execute(
                select(PeriodicPref).where(
                    PeriodicPref.user_id == user.id,
                    PeriodicPref.msg_type == msg_type,
                )
            )
            pref = pref_result.scalar_one_or_none()
            if pref and pref.is_disabled:
                continue

            try:
                await bot.send_message(user.telegram_id, message)
            except Exception:
                continue

            # Update last sent
            if pref:
                pref.last_sent_at = datetime.now(timezone.utc)
            else:
                session.add(PeriodicPref(
                    user_id=user.id,
                    msg_type=msg_type,
                    last_sent_at=datetime.now(timezone.utc),
                ))
            await session.commit()

    await bot.session.close()
    logger.info("Sent periodic '%s' to %d free users", msg_type, len(users))


# ── Scheduler ──


async def reminders_loop():
    """Run reminder and periodic checks daily."""
    while True:
        # Wait until next check time (run at 10:00 UTC daily)
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()

        logger.info("Next reminder check at %s (in %.1f hours)", next_run, wait_seconds / 3600)

        await asyncio.sleep(wait_seconds)

        try:
            await send_reminders()
            await send_periodic_messages()
        except Exception:
            logger.exception("Reminder task failed")

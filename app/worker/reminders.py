"""Reminders and periodic messages scheduler."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import settings
from app.db.models import User, Reminder, PeriodicPref
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# ── Reminders ──

# Типы напоминаний с кнопкой апгрейда «🎯 Тарифы» (T4.3/T4.4/T4.6/T7.2).
_UPGRADE_KB_TYPES = {"trial_ending", "trial_expired", "winback_missed"}

GRACE_DAYS = 7  # T7.1: сколько дней после истечения платный доступ сохраняется (мягкий grace)


def _upgrade_kb() -> InlineKeyboardMarkup:
    from app.config import settings
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"🎯 Тарифы — от ${settings.price_start_monthly_usd}/мес",
        callback_data="menu:plan")]])


def _reminder_kb(rtype: str, user_plan: str | None = None):
    """Клавиатура напоминания: апгрейд / re-engage / продление текущего плана."""
    if rtype in _UPGRADE_KB_TYPES:
        return _upgrade_kb()
    if rtype == "inactive":
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="🔍 Поиск клиентов", callback_data="menu:search")]])
    if rtype in ("subscription_ending", "subscription_expired") and user_plan in ("start", "pro", "business"):
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить", callback_data=f"pay_plan:{user_plan}")],
            [InlineKeyboardButton(text="📋 Другие тарифы", callback_data="menu:plan")],
        ])
    return None


REMINDER_MESSAGES = {
    # trial_ending — ДО истечения (T4.3): предупредить, пока доступ ещё есть
    "trial_ending": {
        2: "⏳ Пробный период заканчивается через 2 дня.\n"
           "Потом контакты клиентов скроются. Сохрани доступ — тариф Старт от ${start}/мес.",
        1: "⏳ Завтра пробный период закончится.\n"
           "Заявки останутся, но без контактов. Тариф Старт (${start}/мес) оставит их открытыми.",
    },
    "trial_expired": {
        1: "⏰ Пробный период закончился. Заявки приходят, но контакты скрыты.\n"
           "Открой их снова — тариф Старт от ${start}/мес.",
        3: "🔒 3 дня без контактов. Каждая заявка уходит тому, кто ответил первым.\n"
           "Верни доступ — от ${start}/мес.",
        7: "📊 Неделя на Free. Заявки видны, а отправитель — нет.\n"
           "Открой контакты — тариф Старт от ${start}/мес.",
    },
    # subscription_ending — ДО истечения (T4.6): продли без перерыва
    "subscription_ending": {
        5: "⏳ Подписка заканчивается через 5 дней.\n"
           "Продли, чтобы получать заявки без перерыва.",
    },
    "subscription_expired": {
        1: "⏰ Подписка закончилась. Контакты снова скрыты.\n"
           "Продли, чтобы отвечать клиентам первым.",
        3: "🔒 3 дня без подписки. Заявки приходят, но без контактов.\n"
           "Верни доступ — продли подписку.",
        7: "📊 Неделя без подписки. Клиенты по-прежнему пишут в чатах.\n"
           "Продли, чтобы видеть их контакты.",
    },
    "inactive": {
        14: "👋 Давно не виделись! За 2 недели появились новые заявки по твоим направлениям. Загляни!",
        28: "📊 Месяц без активности. Твои подписки всё ещё работают — может, настроим новые направления?",
    },
    # winback_missed — реактивация бывших платящих (T7.2): цифра пропущенного в СВОЕЙ нише
    "winback_missed": {
        14: "📊 За 2 недели без подписки в твоей нише прошло {missed} заявок — "
            "ты их видел, но контакты были скрыты.\n"
            "Верни доступ и отвечай первым — тариф Старт от ${start}/мес.",
        28: "📊 Месяц без подписки: {missed} заявок в твоей нише прошли мимо (контакты скрыты).\n"
            "Каждая — клиент, которому ответил кто-то другой. Верни доступ от ${start}/мес.",
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

        # T7.1: downgrade платных после grace (доступ реально истекает; подписки-ниша СОХРАНЯЮТСЯ).
        # subscription_expired (дни 1/3/7) успевают отработать в grace-окне до даунгрейда.
        expired_paid = (await session.execute(
            select(User).where(
                User.plan.in_(["start", "pro", "business"]),
                User.plan_expires_at.isnot(None),
                User.plan_expires_at < today - timedelta(days=GRACE_DAYS),
            )
        )).scalars().all()
        for user in expired_paid:
            user.plan = "free"
            logger.info("Paid plan expired for user %d (>%dd) → free (subs kept)",
                        user.telegram_id, GRACE_DAYS)
        if expired_paid:
            await session.commit()
            from app.cache.subscription_cache import invalidate_all_subscription_caches
            await invalidate_all_subscription_caches()

        # trial_ending (ДО истечения) — для активных триалов (T4.3)
        active_trial = (await session.execute(
            select(User).where(
                User.plan == "trial",
                User.plan_expires_at.isnot(None),
            )
        )).scalars().all()
        for user in active_trial:
            days_until = (user.plan_expires_at.date() - today).days
            if days_until in (2, 1):
                await _maybe_send(session, user, "trial_ending", days_until)

        # Бывшие платные/триалы (free + expiry в прошлом; never-trial free имеют expiry=NULL).
        # Разграничение (T7.2): есть оплаченная Subscription → бывший ПЛАТЯЩИЙ (winback_missed);
        # нет → бывший ТРИАЛ (trial_expired). Иначе платящий получил бы «пробный период закончился».
        from app.db.crud import get_paid_subscriber_ids, count_leads_since
        paid_ids = await get_paid_subscriber_ids(session)
        former = (await session.execute(
            select(User).where(
                User.plan == "free",
                User.plan_expires_at.isnot(None),
            )
        )).scalars().all()
        for user in former:
            days_since = (today - user.plan_expires_at.date()).days
            if user.id in paid_ids:
                # T7.2: реактивация бывшего платящего — цифра пропущенного в нише
                if days_since in (14, 28):
                    missed = await count_leads_since(session, user.id, user.plan_expires_at)
                    if missed > 0:
                        await _maybe_send(session, user, "winback_missed", days_since, missed=missed)
            else:
                # бывший триал (T4.3-фикс: раньше выборка plan=='trial' → срабатывало НИКОГДА)
                if days_since in (1, 3, 7):
                    await _maybe_send(session, user, "trial_expired", days_since)

        # subscription_ending (ДО истечения, за 5 дней) — активные платные, вкл. start (T4.6)
        active_paid = (await session.execute(
            select(User).where(
                User.plan.in_(["start", "pro", "business"]),
                User.plan_expires_at.isnot(None),
                User.plan_expires_at >= today,
            )
        )).scalars().all()
        for user in active_paid:
            days_until = (user.plan_expires_at.date() - today).days
            if days_until == 5:
                await _maybe_send(session, user, "subscription_ending", 5)

        # subscription_expired (ПОСЛЕ истечения) — вкл. start (T4.6-фикс: раньше только pro/business)
        expired_users = (await session.execute(
            select(User).where(
                User.plan.in_(["start", "pro", "business"]),
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


async def _maybe_send(session, user: User, rtype: str, day: int, missed: int | None = None):
    """Send reminder if not already sent and not disabled. `missed` — для winback_missed (T7.2)."""
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
    fmt = {"start": settings.price_start_monthly_usd}
    if missed is not None:
        fmt["missed"] = missed
    if "{" in message:
        message = message.format(**fmt)
    kb = _reminder_kb(rtype, getattr(user, "plan", None))
    if rtype == "winback_missed":
        from app.cache.subscription_cache import record_paywall
        await record_paywall("winback")  # T7.3: метрика реактивации

    # Send via Bot API
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(user.telegram_id, message, reply_markup=kb)
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

    # CTA-подвал (T4.4): контакты открыты на платном тарифе — Старт от $N.
    message += (f"\n\n🔒 Контакты авторов открыты на платном тарифе — "
                f"Старт от ${settings.price_start_monthly_usd}/мес.")
    kb = _upgrade_kb()
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
                await bot.send_message(user.telegram_id, message, reply_markup=kb)
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

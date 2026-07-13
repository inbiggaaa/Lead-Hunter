"""Payment handlers: plan selection, periods (1m/3m/1y), Stars + CryptoBot."""

import asyncio, datetime, logging
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery
from app.config import settings
from app.db.crud import get_user
from app.db.models import Subscription
from app.db.session import get_session
from app.payments.stars import StarsPaymentProvider
from app.payments.cryptobot import CryptoBotPaymentProvider

logger = logging.getLogger(__name__)
router = Router()

PLANS = {"start": {"name": "Старт", "usd_monthly": settings.price_start_monthly_usd},
         "pro": {"name": "Профи", "usd_monthly": settings.price_pro_monthly_usd},
         "business": {"name": "Бизнес", "usd_monthly": settings.price_business_monthly_usd}}
PERIODS = {"1m": {"label": "1 месяц", "months": 1, "discount": 0},
           "3m": {"label": "3 месяца (-10%)", "months": 3, "discount": 0.10},
           "1y": {"label": "1 год (-20%)", "months": 12, "discount": 0.20}}
STARS_PER_USD = settings.stars_per_usd

def _calc(plan_key, period_key):
    base = PLANS[plan_key]["usd_monthly"]; p = PERIODS[period_key]
    total = base * p["months"] * (1 - p["discount"])
    return {"total": total, "per_month": total / p["months"], "stars": int(total * STARS_PER_USD),
            "months": p["months"], "plan_name": PLANS[plan_key]["name"], "period_label": p["label"]}

@router.callback_query(F.data == "menu:plan")
async def on_plan_menu(callback: CallbackQuery):
    async for s in get_session():
        u = await get_user(s, callback.from_user.id)
        pn = u.plan.capitalize() if u else "Free"; await s.commit()
    pro, biz = PLANS["pro"]["usd_monthly"], PLANS["business"]["usd_monthly"]
    text = f"💰 Тариф и оплата\n\nТвой тариф: {pn}\n\n🚀 Pro — от ${pro}/мес\n💎 Business — от ${biz}/мес\n\nСкидки: 3 мес = -10%, 1 год = -20%"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Pro", callback_data="pay_plan:pro")],
        [InlineKeyboardButton(text="💎 Business", callback_data="pay_plan:business")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")]])
    await callback.message.edit_text(text, reply_markup=kb); await callback.answer()

@router.callback_query(F.data.startswith("pay_plan:"))
async def on_period_select(callback: CallbackQuery):
    plan = callback.data.split(":")[1]
    text = f"💳 {PLANS[plan]['name']} — выбери срок:\n\n"; kb_rows = []
    for key, p in PERIODS.items():
        info = _calc(plan, key)
        text += f"• {p['label']}: ${info['total']:.0f} (${info['per_month']:.0f}/мес)\n"
        kb_rows.append([InlineKeyboardButton(text=f"{p['label']} — ${info['total']:.0f}", callback_data=f"pay_period:{plan}:{key}")])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:plan")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)); await callback.answer()

@router.callback_query(F.data.startswith("pay_period:"))
async def on_pay_method(callback: CallbackQuery):
    parts = callback.data.split(":"); plan, period_key = parts[1], parts[2]; info = _calc(plan, period_key)
    text = f"💳 Оплата {info['plan_name']}\n\nСрок: {info['period_label']}\nСумма: ${info['total']:.0f}\n\nВыбери способ оплаты:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_exec:stars:{plan}:{period_key}")],
        [InlineKeyboardButton(text="₮ CryptoBot", callback_data=f"pay_exec:crypto:{plan}:{period_key}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"pay_plan:{plan}")]])
    await callback.message.edit_text(text, reply_markup=kb); await callback.answer()

@router.callback_query(F.data.startswith("pay_exec:"))
async def on_pay_execute(callback: CallbackQuery):
    _, method, plan, period_key = callback.data.split(":"); info = _calc(plan, period_key)
    if method == "stars":
        try: await StarsPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:{period_key}", info["stars"], info["total"])
        except Exception as e: logger.exception("Stars"); await callback.answer(f"Ошибка: {e}", show_alert=True)
    elif method == "crypto":
        if not settings.cryptobot_api_token: await callback.answer("CryptoBot не настроен", show_alert=True); return
        try:
            r = await CryptoBotPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:{period_key}", info["stars"], info["total"])
            pay_link = r.get("bot_invoice_url") or r.get("pay_url", "")
            await callback.message.edit_text(
                f"💳 Счёт создан!\n\nСумма: ${info['total']:.0f}\n\nОплати по кнопке ниже — тариф активируется автоматически.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=pay_link)],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data=f"pay_plan:{plan}")]]))
            from app.worker.payment_checker import add_pending
            await add_pending(r["invoice_id"], await _get_user_id(callback), plan, period_key, callback.from_user.id)
        except Exception as e: logger.exception("CryptoBot"); await callback.answer(f"Ошибка: {e}", show_alert=True)
    await callback.answer()

@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery): await query.answer(ok=True)

@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split(":")
    if len(parts) >= 4 and parts[0] == "sub": await _activate_by_msg(message, parts[1], parts[2], "stars", payload)

async def _apply_referral_bonus(user_id: int):
    """Give bonus days to referrer when referral pays."""
    from app.db.session import async_session_factory
    from app.db.models import Referral, User
    from sqlalchemy import select
    import datetime as dt
    from app.config import settings

    async with async_session_factory() as s:
        ref = (await s.execute(
            select(Referral).where(Referral.referral_id == user_id, Referral.status == "pending")
        )).scalar_one_or_none()
        if not ref:
            return

        ref.status = "paid"
        ref.activated_at = dt.datetime.now(dt.timezone.utc)

        referrer = (await s.execute(
            select(User).where(User.id == ref.referrer_id)
        )).scalar_one_or_none()

        if referrer and referrer.plan in ("start", "pro", "business", "trial"):
            if referrer.plan_expires_at:
                referrer.plan_expires_at += dt.timedelta(days=settings.referral_bonus_days)
            else:
                referrer.plan_expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.referral_bonus_days)

        await s.commit()

        # Notify referrer
        if referrer:
            from aiogram import Bot
            bot = Bot(token=settings.bot_token)
            try:
                new_expiry = referrer.plan_expires_at.strftime("%d.%m.%Y") if referrer.plan_expires_at else "—"
                await bot.send_message(
                    referrer.telegram_id,
                    f"🎁 Ваш реферал оплатил подписку!\n\n"
                    f"➕ {settings.referral_bonus_days} дней добавлено к вашему тарифу.\n"
                    f"📅 Подписка действует до: {new_expiry}"
                )
            except Exception:
                pass
            finally:
                await bot.session.close()

        # Notify admin
        if referrer:
            from app.worker.notify_admin import notify_admin
            ref_name = f"@{referrer.username}" if referrer.username else f"ID:{referrer.telegram_id}"
            await notify_admin(
                f"🎁 Реферал оплатил!\n\n👤 Реферер: {ref_name}\n➕ +{settings.referral_bonus_days} дней"
            )

async def _activate_by_msg(message, plan, period_key, method, invoice_id):
    info = _calc(plan, period_key)
    async for s in get_session():
        u = await get_user(s, message.from_user.id)
        if not u: return
        now = datetime.datetime.now(datetime.timezone.utc); exp = now + datetime.timedelta(days=30 * info["months"])
        s.add(Subscription(user_id=u.id, plan=plan, period=period_key, expires_at=exp, payment_method=method, payment_status="paid", invoice_id=invoice_id, amount=info["total"]))
        u.plan = plan; u.plan_activated_at = now; u.plan_expires_at = exp; await s.commit()
    await _apply_referral_bonus(message.from_user.id)
    from app.userbot.discovery import notify_new_subscription
    info2 = _calc(plan, period_key)
    asyncio.create_task(notify_new_subscription(message.from_user.username, message.from_user.id, plan, period_key, "direct", info2["total"]))
    await message.answer(f"✅ Оплата прошла! Тариф: {info['plan_name']}\nСрок: {info['period_label']}\nДействует до: {exp.strftime('%d.%m.%Y')}")

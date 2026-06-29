"""Payment handlers: plan selection, periods (1m/3m/1y), Stars + CryptoBot."""

import datetime
import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
)

from app.config import settings
from app.db.crud import get_user
from app.db.models import Subscription
from app.db.session import get_session
from app.payments.stars import StarsPaymentProvider
from app.payments.cryptobot import CryptoBotPaymentProvider

logger = logging.getLogger(__name__)
router = Router()

PLANS = {
    "pro": {"name": "Pro", "usd_monthly": settings.price_pro_monthly_usd},
    "business": {"name": "Business", "usd_monthly": settings.price_business_monthly_usd},
}

PERIODS = {
    "1m": {"label": "1 месяц", "months": 1, "discount": 0},
    "3m": {"label": "3 месяца (-10%)", "months": 3, "discount": 0.10},
    "1y": {"label": "1 год (-20%)", "months": 12, "discount": 0.20},
}

STARS_PER_USD = 100  # 1 USD = 100 Telegram Stars


def _calc(plan_key: str, period_key: str) -> dict:
    """Calculate price info for a plan+period combination."""
    base = PLANS[plan_key]["usd_monthly"]
    p = PERIODS[period_key]
    total = base * p["months"] * (1 - p["discount"])
    return {
        "total": total,
        "per_month": total / p["months"],
        "stars": int(total * STARS_PER_USD),
        "months": p["months"],
        "plan_name": PLANS[plan_key]["name"],
        "period_label": p["label"],
    }


# ── Plan screen ──

@router.callback_query(F.data == "menu:plan")
async def on_plan_menu(callback: CallbackQuery):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        plan_name = user.plan.capitalize() if user else "Free"
        await session.commit()

    pro = PLANS["pro"]["usd_monthly"]
    biz = PLANS["business"]["usd_monthly"]

    text = f"💰 Тариф и оплата\n\nТвой тариф: {plan_name}\n\n"
    text += f"🚀 Pro — от ${pro}/мес\n"
    text += f"💎 Business — от ${biz}/мес\n"
    text += "\nСкидки: 3 мес = -10%, 1 год = -20%"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Pro", callback_data="pay_plan:pro")],
        [InlineKeyboardButton(text="💎 Business", callback_data="pay_plan:business")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Period selection ──

@router.callback_query(F.data.startswith("pay_plan:"))
async def on_period_select(callback: CallbackQuery):
    plan = callback.data.split(":")[1]

    text = f"💳 {PLANS[plan]['name']} — выбери срок:\n\n"
    kb_rows = []
    for key, p in PERIODS.items():
        info = _calc(plan, key)
        text += f"• {p['label']}: ${info['total']:.0f} (${info['per_month']:.0f}/мес)\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"{p['label']} — ${info['total']:.0f}",
            callback_data=f"pay_period:{plan}:{key}",
        )])
    kb_rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:plan")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Payment method ──

@router.callback_query(F.data.startswith("pay_period:"))
async def on_pay_method(callback: CallbackQuery):
    parts = callback.data.split(":")
    plan, period_key = parts[1], parts[2]
    info = _calc(plan, period_key)

    text = (
        f"💳 Оплата {info['plan_name']}\n\n"
        f"Срок: {info['period_label']}\n"
        f"Сумма: ${info['total']:.0f}\n\n"
        f"Выбери способ оплаты:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Telegram Stars ({info['stars']} ⭐)",
            callback_data=f"pay_exec:stars:{plan}:{period_key}",
        )],
        [InlineKeyboardButton(
            text=f"₮ CryptoBot (${info['total']:.0f})",
            callback_data=f"pay_exec:crypto:{plan}:{period_key}",
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"pay_plan:{plan}")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Execute payment ──

@router.callback_query(F.data.startswith("pay_exec:"))
async def on_pay_execute(callback: CallbackQuery):
    _, method, plan, period_key = callback.data.split(":")
    info = _calc(plan, period_key)

    if method == "stars":
        provider = StarsPaymentProvider()
        try:
            await provider.create_invoice(
                user_id=callback.from_user.id,
                plan=f"{plan}:{period_key}",
                amount_stars=info["stars"],
                amount_usd=info["total"],
            )
        except Exception as e:
            logger.exception("Stars invoice failed")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    elif method == "crypto":
        if not settings.cryptobot_api_token:
            await callback.answer("CryptoBot не настроен", show_alert=True)
            return
        provider = CryptoBotPaymentProvider()
        try:
            invoice_id = await provider.create_invoice(
                user_id=callback.from_user.id,
                plan=f"{plan}:{period_key}",
                amount_stars=info["stars"],
                amount_usd=info["total"],
            )
            pay_link = f"https://t.me/send?start=IV{invoice_id}"
            await callback.message.edit_text(
                f"💳 Счёт CryptoBot создан!\n\n"
                f"Сумма: ${info['total']:.0f}\n"
                f"Оплати по ссылке:\n{pay_link}\n\n"
                f"После оплаты нажми кнопку проверки.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"pay_check:crypto:{invoice_id}:{plan}:{period_key}",
                    )],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data=f"pay_plan:{plan}")],
                ]),
            )
        except Exception as e:
            logger.exception("CryptoBot invoice failed")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    await callback.answer()


# ── Check CryptoBot payment ──

@router.callback_query(F.data.startswith("pay_check:crypto:"))
async def on_pay_check(callback: CallbackQuery):
    _, _, invoice_id, plan, period_key = callback.data.split(":")
    provider = CryptoBotPaymentProvider()
    paid = await provider.check_payment(invoice_id)
    if paid:
        await _activate(callback, plan, period_key, "cryptobot", invoice_id)
    else:
        await callback.answer("Оплата ещё не прошла. Попробуй позже.", show_alert=True)


# ── Pre-checkout (Stars) ──

@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


# ── Successful payment (Stars) ──

@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload  # "sub:plan:period:user_id"
    parts = payload.split(":")
    if len(parts) >= 4 and parts[0] == "sub":
        plan = parts[1]
        period_key = parts[2]
        await _activate_by_msg(message, plan, period_key, "stars", payload)


async def _activate(callback: CallbackQuery, plan: str, period_key: str, method: str, invoice_id: str):
    info = _calc(plan, period_key)
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30 * info["months"])
        sub = Subscription(
            user_id=user.id, plan=plan, period=period_key, expires_at=expires,
            payment_method=method, payment_status="paid", invoice_id=invoice_id,
            amount=info["total"],
        )
        session.add(sub)
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        await session.commit()

    await callback.message.edit_text(
        f"✅ Оплата прошла!\n\nТариф: {info['plan_name']}\nСрок: {info['period_label']}\n"
        f"Действует до: {expires.strftime('%d.%m.%Y')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
    )


async def _activate_by_msg(message: Message, plan: str, period_key: str, method: str, invoice_id: str):
    info = _calc(plan, period_key)
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30 * info["months"])
        sub = Subscription(
            user_id=user.id, plan=plan, period=period_key, expires_at=expires,
            payment_method=method, payment_status="paid", invoice_id=invoice_id,
            amount=info["total"],
        )
        session.add(sub)
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        await session.commit()
    await message.answer(
        f"✅ Оплата прошла! Тариф: {info['plan_name']}\nСрок: {info['period_label']}\n"
        f"Действует до: {expires.strftime('%d.%m.%Y')}"
    )

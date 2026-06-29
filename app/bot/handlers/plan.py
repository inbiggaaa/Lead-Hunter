"""Payment handlers: pre_checkout_query, successful_payment, plan/payment flow."""

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
    "pro": {"name": "Pro", "usd": settings.price_pro_monthly_usd},
    "business": {"name": "Business", "usd": settings.price_business_monthly_usd},
}

STARS_PER_USD = 100  # 1 USD = 100 Telegram Stars (XTR)


# ── Plan screen (prices in USD) ──

@router.callback_query(F.data == "menu:plan")
async def on_plan_menu(callback: CallbackQuery):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        plan_name = user.plan.capitalize() if user else "Free"
        await session.commit()

    pro = PLANS["pro"]
    biz = PLANS["business"]

    text = f"💰 Тариф и оплата\n\nТвой тариф: {plan_name}\n\n"
    text += f"🚀 Pro — ${pro['usd']}/мес\n"
    text += f"💎 Business — ${biz['usd']}/мес"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Pro — ${pro['usd']}/мес", callback_data="pay:pro")],
        [InlineKeyboardButton(text=f"💎 Business — ${biz['usd']}/мес", callback_data="pay:business")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Payment method selection ──

@router.callback_query(F.data.startswith("pay:"))
async def on_pay_select(callback: CallbackQuery):
    plan = callback.data.split(":")[1]
    plan_info = PLANS[plan]
    stars_amount = plan_info["usd"] * STARS_PER_USD

    text = f"💳 Оплата {plan_info['name']}\n\nСумма: ${plan_info['usd']}\nВыбери способ оплаты:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐ Telegram Stars ({stars_amount} ⭐)",
            callback_data=f"pay_exec:stars:{plan}",
        )],
        [InlineKeyboardButton(
            text=f"₮ CryptoBot (${plan_info['usd']})",
            callback_data=f"pay_exec:crypto:{plan}",
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:plan")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Execute payment ──

@router.callback_query(F.data.startswith("pay_exec:"))
async def on_pay_execute(callback: CallbackQuery):
    _, method, plan = callback.data.split(":")
    plan_info = PLANS[plan]
    stars_amount = plan_info["usd"] * STARS_PER_USD

    if method == "stars":
        provider = StarsPaymentProvider()
        try:
            await provider.create_invoice(
                user_id=callback.from_user.id,
                plan=plan,
                amount_stars=stars_amount,
                amount_usd=plan_info["usd"],
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
                plan=plan,
                amount_stars=stars_amount,
                amount_usd=plan_info["usd"],
            )
            pay_link = f"https://t.me/send?start=IV{invoice_id}"
            await callback.message.edit_text(
                f"💳 Счёт CryptoBot создан!\n\n"
                f"Сумма: ${plan_info['usd']}\n"
                f"Оплати по ссылке:\n{pay_link}\n\n"
                f"После оплаты нажми кнопку проверки.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"pay_check:crypto:{invoice_id}:{plan}",
                    )],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:plan")],
                ]),
            )
        except Exception as e:
            logger.exception("CryptoBot invoice failed")
            await callback.answer(f"Ошибка: {e}", show_alert=True)

    await callback.answer()


# ── Check CryptoBot payment ──

@router.callback_query(F.data.startswith("pay_check:crypto:"))
async def on_pay_check(callback: CallbackQuery):
    _, _, invoice_id, plan = callback.data.split(":")
    provider = CryptoBotPaymentProvider()

    paid = await provider.check_payment(invoice_id)
    if paid:
        await _activate_subscription(callback, plan, "cryptobot", invoice_id)
    else:
        await callback.answer("Оплата ещё не прошла. Попробуй позже.", show_alert=True)


# ── Pre-checkout (Stars) ──

@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


# ── Successful payment (Stars) ──

@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload  # "sub:plan:user_id"
    parts = payload.split(":")
    if len(parts) >= 3 and parts[0] == "sub":
        plan = parts[1]
        await _activate_subscription_by_message(message, plan, "stars", payload)


async def _activate_subscription(callback: CallbackQuery, plan: str, method: str, invoice_id: str):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30)

        sub = Subscription(
            user_id=user.id, plan=plan, period="monthly", expires_at=expires,
            payment_method=method, payment_status="paid", invoice_id=invoice_id,
            amount=PLANS[plan]["usd"],
        )
        session.add(sub)
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        await session.commit()

    await callback.message.edit_text(
        f"✅ Оплата прошла!\n\nТариф: {plan.title()}\nДействует до: {expires.strftime('%d.%m.%Y')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
    )


async def _activate_subscription_by_message(message: Message, plan: str, method: str, invoice_id: str):
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(days=30)
        sub = Subscription(
            user_id=user.id, plan=plan, period="monthly", expires_at=expires,
            payment_method=method, payment_status="paid", invoice_id=invoice_id,
            amount=PLANS[plan]["usd"],
        )
        session.add(sub)
        user.plan = plan
        user.plan_activated_at = now
        user.plan_expires_at = expires
        await session.commit()

    await message.answer(
        f"✅ Оплата прошла! Тариф: {plan.title()}\nДействует до: {expires.strftime('%d.%m.%Y')}"
    )

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
from app.locales import get_text

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

async def _get_user_id(callback: CallbackQuery) -> int:
    """DB users.id по telegram-пользователю (payment_checker активирует по User.id)."""
    async for s in get_session():
        u = await get_user(s, callback.from_user.id)
        return u.id if u else 0
    return 0

async def _get_lang(callback: CallbackQuery) -> str:
    async for s in get_session():
        u = await get_user(s, callback.from_user.id)
        return u.language if u else "ru"
    return "ru"

def payment_error_kb(plan: str, period_key: str, method: str, lang: str) -> InlineKeyboardMarkup:
    """Клавиатура экрана ошибки оплаты (T2.2): повтор / другой способ / назад."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "pay_err_retry"), callback_data=f"pay_exec:{method}:{plan}:{period_key}")],
        [InlineKeyboardButton(text=get_text(lang, "pay_err_other"), callback_data=f"pay_period:{plan}:{period_key}")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data=f"pay_plan:{plan}")],
    ])

PLAN_DISPLAY = {
    "ru": {"free": "Free", "start": "Старт", "pro": "Профи", "business": "Бизнес", "trial": "Business (триал)"},
    "en": {"free": "Free", "start": "Start", "pro": "Pro", "business": "Business", "trial": "Business (trial)"},
}

def plan_display_name(plan: str, lang: str) -> str:
    return PLAN_DISPLAY.get(lang, PLAN_DISPLAY["ru"]).get(plan, plan.capitalize())

def build_plan_screen(user, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """Единый рендер экрана «Тариф и оплата» (T3.1) — для menu:plan и /plan.
    Цены — из settings (PLANS); текущий план отмечается галочкой."""
    current = user.plan if user else "free"
    text = (
        f"{get_text(lang, 'plan_title')}\n\n"
        f"{get_text(lang, 'plan_current', plan=plan_display_name(current, lang))}\n\n"
        f"{get_text(lang, 'plan_card_start', price=PLANS['start']['usd_monthly'])}\n\n"
        f"{get_text(lang, 'plan_card_pro', price=PLANS['pro']['usd_monthly'])}\n\n"
        f"{get_text(lang, 'plan_card_business', price=PLANS['business']['usd_monthly'])}\n\n"
        f"{get_text(lang, 'plan_discounts')}"
    )
    rows = []
    for plan_key in ("start", "pro", "business"):
        price = PLANS[plan_key]["usd_monthly"]
        if plan_key == current:
            label = get_text(lang, "plan_btn_current", name=plan_display_name(plan_key, lang))
        else:
            label = get_text(lang, f"plan_btn_{plan_key}", price=price)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"pay_plan:{plan_key}")])
    rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)

# Контекстные пейволлы (T4.1): минимальный план, снимающий лимит триггера,
# по текущему плану. direction/geo/channel у free и start одинаковы → сразу pro.
_UPGRADE_PATH = {
    "keyword":   {"free": "start", "start": "pro", "pro": "business"},
    "direction": {"free": "pro", "start": "pro", "pro": "business"},
    "country":   {"free": "pro", "start": "pro", "pro": "business"},
    "city":      {"free": "pro", "start": "pro", "pro": "business"},
    "channel":   {"free": "pro", "start": "pro", "pro": "business"},
    "stats":     {"free": "pro", "start": "pro", "pro": "business"},
}

def next_plan_for(trigger: str, current_plan: str) -> str:
    return _UPGRADE_PATH.get(trigger, {}).get(current_plan, "business")

def paywall_text(trigger: str, current_plan: str, lang: str) -> str:
    """Строка пейволла: что даёт следующий тариф + его цена (для alert'ов воронки)."""
    nxt = next_plan_for(trigger, current_plan)
    return get_text(lang, f"paywall_{trigger}",
                    plan=plan_display_name(nxt, lang), price=PLANS[nxt]["usd_monthly"])

def build_paywall(trigger: str, current_plan: str, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """Полноэкранный пейволл с кнопкой апгрейда на следующий тариф (T4.1)."""
    nxt = next_plan_for(trigger, current_plan)
    text = f"{get_text(lang, 'paywall_title')}\n\n{paywall_text(trigger, current_plan, lang)}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=get_text(lang, f"plan_btn_{nxt}", price=PLANS[nxt]["usd_monthly"]),
            callback_data=f"pay_plan:{nxt}")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    return text, kb

@router.callback_query(F.data == "menu:plan")
async def on_plan_menu(callback: CallbackQuery):
    async for s in get_session():
        u = await get_user(s, callback.from_user.id)
        lang = u.language if u else "ru"
        text, kb = build_plan_screen(u, lang)
        await s.commit()
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
        except Exception:
            logger.exception("Stars")
            lang = await _get_lang(callback)
            await callback.message.edit_text(get_text(lang, "pay_error_body"),
                                             reply_markup=payment_error_kb(plan, period_key, "stars", lang))
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
        except Exception:
            logger.exception("CryptoBot")
            lang = await _get_lang(callback)
            await callback.message.edit_text(get_text(lang, "pay_error_body"),
                                             reply_markup=payment_error_kb(plan, period_key, "crypto", lang))
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

async def maybe_offer_annual(db_user_id: int, telegram_id: int, plan: str, period_key: str):
    """T4.5: на 2-м подряд МЕСЯЧНОМ платеже одного плана — однократно предложить годовую (−20%)."""
    if period_key != "1m":
        return
    from app.cache import get_redis
    redis = await get_redis()
    flag = f"upsell:annual:{telegram_id}"
    if await redis.get(flag):
        return  # уже предлагали

    from sqlalchemy import func, select as sa_select
    async for s in get_session():
        cnt = (await s.execute(sa_select(func.count(Subscription.id)).where(
            Subscription.user_id == db_user_id, Subscription.plan == plan,
            Subscription.period == "1m", Subscription.payment_status == "paid"))).scalar() or 0
    if cnt < 2:
        return

    await redis.set(flag, "1")
    year = _calc(plan, "1y")
    monthly_year = PLANS[plan]["usd_monthly"] * 12
    text = (f"💡 Помесячно ты платишь ${monthly_year:.0f} за год.\n"
            f"Годовая {PLANS[plan]['name']} — ${year['total']:.0f} (−20%, ≈2 месяца в подарок).")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"💳 Годовая — ${year['total']:.0f}", callback_data=f"pay_period:{plan}:1y")]])
    from aiogram import Bot
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(telegram_id, text, reply_markup=kb)
    except Exception:
        logger.exception("Annual upsell send failed for %d", telegram_id)
    finally:
        await bot.session.close()

async def _activate_by_msg(message, plan, period_key, method, invoice_id):
    # Политика (#81): оплата всегда устанавливает оплаченный план и срок 30×months
    # ОТ ТЕКУЩЕГО МОМЕНТА. Оплата более дешёвого плана при активном дорогом = даунгрейд
    # с новой датой (осознанный выбор пользователя; апселл верхних тарифов — на экране).
    info = _calc(plan, period_key)
    async for s in get_session():
        u = await get_user(s, message.from_user.id)
        if not u: return
        now = datetime.datetime.now(datetime.timezone.utc); exp = now + datetime.timedelta(days=30 * info["months"])
        s.add(Subscription(user_id=u.id, plan=plan, period=period_key, expires_at=exp, payment_method=method, payment_status="paid", invoice_id=invoice_id, amount=info["total"]))
        u.plan = plan; u.plan_activated_at = now; u.plan_expires_at = exp; await s.commit()
        user_db_id = u.id
    # Смена плана меняет формат уведомлений (Free скрывает контакты) — сбросить
    # кэш подписок сразу, иначе оплаченный пользователь до TTL (1ч) видел бы Free.
    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()
    await _apply_referral_bonus(message.from_user.id)
    from app.userbot.discovery import notify_new_subscription
    info2 = _calc(plan, period_key)
    asyncio.create_task(notify_new_subscription(message.from_user.username, message.from_user.id, plan, period_key, "direct", info2["total"]))
    await message.answer(f"✅ Оплата прошла! Тариф: {info['plan_name']}\nСрок: {info['period_label']}\nДействует до: {exp.strftime('%d.%m.%Y')}")
    await maybe_offer_annual(user_db_id, message.from_user.id, plan, period_key)

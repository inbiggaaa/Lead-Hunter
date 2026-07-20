"""Payment handlers: plan selection, periods (1m/3m/1y), Stars + CryptoBot."""

import asyncio, datetime, logging, html
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery
from app.config import settings
from app.db.crud import get_user
from app.db.models import Subscription
from app.db.session import get_session
from app.payments.stars import StarsPaymentProvider
from app.payments.cryptobot import CryptoBotPaymentProvider
from app.locales import get_text, normalize_language
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = Router()

PLANS = {"start": {"name": "Start", "usd_monthly": settings.price_start_monthly_usd},
         "pro": {"name": "Pro", "usd_monthly": settings.price_pro_monthly_usd},
         "business": {"name": "Business", "usd_monthly": settings.price_business_monthly_usd}}
PERIODS = {"1m": {"label": "1 месяц", "months": 1, "discount": 0},
           "3m": {"label": "3 месяца (-10%)", "months": 3, "discount": 0.10},
           "1y": {"label": "1 год (-20%)", "months": 12, "discount": 0.20}}
STARS_PER_USD = settings.stars_per_usd

def _calc(plan_key, period_key):
    base = PLANS[plan_key]["usd_monthly"]; p = PERIODS[period_key]
    total = base * p["months"] * (1 - p["discount"])
    return {"total": total, "full_total": base * p["months"], "savings": base * p["months"] - total, "per_month": total / p["months"], "stars": int(total * STARS_PER_USD),
            "months": p["months"], "plan_name": PLANS[plan_key]["name"], "period_label": p["label"]}

def _calc_winback(plan_key: str):
    """Three months with the one-time 25% winback discount."""
    base = PLANS[plan_key]["usd_monthly"]
    total = base * 3 * 0.75
    return {"total": total, "per_month": total / 3, "stars": int(total * STARS_PER_USD),
            "months": 3, "plan_name": PLANS[plan_key]["name"], "period_label": "3m_winback"}

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
    "ru": {"free": "Free", "start": "Start", "pro": "Pro", "business": "Business", "trial": "Trial"},
    "en": {"free": "Free", "start": "Start", "pro": "Pro", "business": "Business", "trial": "Trial"},
}

def plan_display_name(plan: str, lang: str) -> str:
    return PLAN_DISPLAY.get(lang, PLAN_DISPLAY["ru"]).get(plan, plan.capitalize())

def period_display_name(period_key: str, lang: str) -> str:
    return get_text(lang, f"period_{period_key}")

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
    "csv":       {"free": "business", "start": "business", "pro": "business"},
}

def next_plan_for(trigger: str, current_plan: str) -> str:
    return _UPGRADE_PATH.get(trigger, {}).get(current_plan, "business")

def paywall_text(trigger: str, current_plan: str, lang: str) -> str:
    """Строка пейволла: что даёт следующий тариф + его цена (для alert'ов воронки)."""
    nxt = next_plan_for(trigger, current_plan)
    return get_text(lang, f"paywall_{trigger}",
                    plan=plan_display_name(nxt, lang), price=PLANS[nxt]["usd_monthly"])

async def paywall_screen(trigger: str, current_plan: str, lang: str, user=None) -> tuple[str, InlineKeyboardMarkup]:
    """build_paywall + счётчик показа (T6.4) — единая точка инструментации."""
    from app.cache.subscription_cache import record_paywall
    await record_paywall(trigger)
    from app.analytics import record_event
    await record_event("paywall_viewed", user, trigger=trigger, context={"trigger": trigger, "target_plan": next_plan_for(trigger, current_plan)})
    return build_paywall(trigger, current_plan, lang)


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

@router.callback_query(F.data.startswith("lead:unlock:"))
async def on_lead_unlock(callback: CallbackQuery):
    token = callback.data.split(":", 2)[2]
    async for s in get_session():
        user = await get_user(s, callback.from_user.id)
    lang = user.language if user else "ru"
    from app.analytics import get_lead_paywall_context, record_event
    context = await get_lead_paywall_context(user.id, token) if user else None
    preview = html.escape((context or {}).get("preview", ""))
    text = get_text(lang, "lead_paywall_title")
    if preview: text += "\n\n" + get_text(lang, "lead_paywall_preview", preview=preview)
    text += "\n\n" + get_text(lang, "lead_paywall_access")
    await record_event("paywall_viewed", user, trigger="lead", context={"trigger": "lead", "target_plan": "start", "lead_id": token})
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text(lang, "plan_btn_start", price=PLANS["start"]["usd_monthly"]), callback_data="pay_plan:start")], [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")]])
    await callback.message.edit_text(text, reply_markup=kb); await callback.answer()

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
    lang = await _get_lang(callback)
    async for s in get_session():
        analytics_user = await get_user(s, callback.from_user.id)
    from app.analytics import record_event
    await record_event("plan_selected", analytics_user, context={"target_plan": plan})
    text = get_text(lang, "payment_period_title", plan=plan_display_name(plan, lang)) + "\n\n"; kb_rows = []
    for key, p in PERIODS.items():
        info = _calc(plan, key)
        period = period_display_name(key, lang)
        if key == "1m":
            text += get_text(lang, "payment_period_line_regular", period=period, total=f"{info['total']:.0f}") + "\n"
        else:
            text += get_text(lang, "payment_period_line", period=period, total=f"{info['total']:.0f}", monthly=f"{info['per_month']:.0f}", savings=f"{info['savings']:.0f}") + "\n"
            if key == "3m": text += get_text(lang, "payment_period_recommended") + "\n"
        kb_rows.append([InlineKeyboardButton(text=get_text(lang, "payment_period_button", period=period, total=f"{info['total']:.0f}"), callback_data=f"pay_period:{plan}:{key}")])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:plan")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)); await callback.answer()

@router.callback_query(F.data.startswith("pay_period:"))
async def on_pay_method(callback: CallbackQuery):
    parts = callback.data.split(":"); plan, period_key = parts[1], parts[2]; info = _calc(plan, period_key)
    lang = await _get_lang(callback)
    async for s in get_session():
        analytics_user = await get_user(s, callback.from_user.id)
    from app.analytics import record_event
    await record_event("period_selected", analytics_user, context={"target_plan": plan, "period": period_key})
    text = get_text(lang, "payment_method_title", plan=plan_display_name(plan, lang), period=period_display_name(period_key, lang), total=f"{info['total']:.0f}")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_exec:stars:{plan}:{period_key}")],
        [InlineKeyboardButton(text="₮ CryptoBot", callback_data=f"pay_exec:crypto:{plan}:{period_key}")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data=f"pay_plan:{plan}")]])
    await callback.message.edit_text(text, reply_markup=kb); await callback.answer()

async def _active_winback_offer(user_id: int):
    from app.db.models import WinbackOffer
    from app.db.session import async_session_factory
    async with async_session_factory() as session:
        offer = (await session.execute(select(WinbackOffer).where(WinbackOffer.user_id == user_id))).scalar_one_or_none()
        now = datetime.datetime.now(datetime.timezone.utc)
        return offer if offer and offer.redeemed_at is None and offer.expires_at > now else None


@router.callback_query(F.data.startswith("winback:buy:"))
async def on_winback_plan(callback: CallbackQuery):
    plan = callback.data.rsplit(":", 1)[1]
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
    lang = normalize_language(getattr(user, "language", None))
    offer = await _active_winback_offer(user.id) if user else None
    if not offer:
        await callback.answer(get_text(lang, "winback_expired"), show_alert=True)
        return
    info = _calc_winback(plan)
    expires = offer.expires_at.astimezone(datetime.timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    text = get_text(lang, "winback_payment_title", plan=plan_display_name(plan, lang), total=f"{info['total']:.2f}", expires=expires)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"winback:pay:stars:{plan}")],
        [InlineKeyboardButton(text="₮ CryptoBot", callback_data=f"winback:pay:crypto:{plan}")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("winback:pay:"))
async def on_winback_pay(callback: CallbackQuery):
    _, _, method, plan = callback.data.split(":")
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
    lang = normalize_language(getattr(user, "language", None))
    offer = await _active_winback_offer(user.id) if user else None
    if not offer:
        await callback.answer(get_text(lang, "winback_expired"), show_alert=True)
        return
    info = _calc_winback(plan)
    if method == "stars":
        await StarsPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:3m:wb25", info["stars"], info["total"])
    elif method == "crypto":
        if not settings.cryptobot_api_token:
            await callback.answer(get_text(lang, "payment_crypto_unavailable"), show_alert=True)
            return
        result = await CryptoBotPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:3m:wb25", info["stars"], info["total"])
        pay_link = result.get("bot_invoice_url") or result.get("pay_url", "")
        await callback.message.edit_text(get_text(lang, "payment_invoice_created", total=f"{info['total']:.2f}"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=get_text(lang, "payment_btn_pay"), url=pay_link)]]))
        from app.worker.payment_checker import add_pending
        await add_pending(result["invoice_id"], user.id, plan, "3m", callback.from_user.id, promo="wb25", amount=info["total"])
    from app.analytics import record_event
    await record_event("winback_offer_clicked", user, context={"target_plan": plan, "period": "3m", "discount": 25})
    await callback.answer()


@router.callback_query(F.data.startswith("pay_exec:"))
async def on_pay_execute(callback: CallbackQuery):
    _, method, plan, period_key = callback.data.split(":"); info = _calc(plan, period_key)
    lang = await _get_lang(callback)
    async for s in get_session():
        analytics_user = await get_user(s, callback.from_user.id)
    from app.analytics import record_event
    await record_event("payment_method_selected", analytics_user, context={"target_plan": plan, "period": period_key, "method": method})
    if method == "stars":
        try: await StarsPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:{period_key}", info["stars"], info["total"])
        except Exception:
            await record_event("payment_failed", analytics_user, context={"target_plan": plan, "period": period_key, "method": method, "success": False})
            logger.exception("Stars")
            lang = await _get_lang(callback)
            await callback.message.edit_text(get_text(lang, "pay_error_body"),
                                             reply_markup=payment_error_kb(plan, period_key, "stars", lang))
    elif method == "crypto":
        if not settings.cryptobot_api_token: await callback.answer(get_text(lang, "payment_crypto_unavailable"), show_alert=True); return
        try:
            r = await CryptoBotPaymentProvider().create_invoice(callback.from_user.id, f"{plan}:{period_key}", info["stars"], info["total"])
            pay_link = r.get("bot_invoice_url") or r.get("pay_url", "")
            await callback.message.edit_text(
                get_text(lang, "payment_invoice_created", total=f"{info['total']:.0f}"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=get_text(lang, "payment_btn_pay"), url=pay_link)],
                    [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data=f"pay_plan:{plan}")]]))
            from app.worker.payment_checker import add_pending
            await add_pending(r["invoice_id"], await _get_user_id(callback), plan, period_key, callback.from_user.id)
        except Exception:
            await record_event("payment_failed", analytics_user, context={"target_plan": plan, "period": period_key, "method": method, "success": False})
            logger.exception("CryptoBot")
            lang = await _get_lang(callback)
            await callback.message.edit_text(get_text(lang, "pay_error_body"),
                                             reply_markup=payment_error_kb(plan, period_key, "crypto", lang))
    await callback.answer()

def parse_stars_payload(payload: str) -> tuple[str, str, int, str | None] | None:
    """Parse Stars invoice payload → (plan, period, telegram_id, promo|None).

    Formats:
      sub:{plan}:{period}:{telegram_id}
      sub:{plan}:{period}:wb25:{telegram_id}
    """
    parts = payload.split(":")
    if len(parts) == 4 and parts[0] == "sub":
        plan, period, tg_raw, promo = parts[1], parts[2], parts[3], None
    elif len(parts) == 5 and parts[0] == "sub" and parts[3] == "wb25":
        plan, period, promo, tg_raw = parts[1], parts[2], parts[3], parts[4]
    else:
        return None
    if plan not in PLANS or period not in PERIODS:
        return None
    try:
        telegram_id = int(tg_raw)
    except ValueError:
        return None
    return plan, period, telegram_id, promo


async def validate_stars_pre_checkout(
    *,
    payload: str,
    from_user_id: int,
    currency: str,
    total_amount: int,
) -> tuple[bool, str]:
    """Validate Stars pre-checkout / successful_payment amounts and ownership."""
    parsed = parse_stars_payload(payload)
    if not parsed:
        return False, "Invalid invoice payload"
    plan, period, telegram_id, promo = parsed
    if from_user_id != telegram_id:
        return False, "User mismatch"
    if currency != "XTR":
        return False, "Invalid currency"
    info = _calc_winback(plan) if promo == "wb25" else _calc(plan, period)
    if int(total_amount) != int(info["stars"]):
        return False, "Amount mismatch"
    if promo == "wb25":
        from app.db.crud import get_user
        from app.db.session import async_session_factory
        async with async_session_factory() as session:
            user = await get_user(session, from_user_id)
            if not user:
                return False, "User not found"
            offer = await _active_winback_offer(user.id)
            if not offer:
                return False, "Winback offer expired"
    return True, ""


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    ok, err = await validate_stars_pre_checkout(
        payload=query.invoice_payload,
        from_user_id=query.from_user.id,
        currency=query.currency,
        total_amount=query.total_amount,
    )
    if not ok:
        logger.warning("Stars pre-checkout rejected for %d: %s", query.from_user.id, err)
        await query.answer(ok=False, error_message=err)
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message):
    sp = message.successful_payment
    ok, err = await validate_stars_pre_checkout(
        payload=sp.invoice_payload,
        from_user_id=message.from_user.id,
        currency=sp.currency,
        total_amount=sp.total_amount,
    )
    if not ok:
        logger.warning(
            "Stars successful_payment rejected for %d: %s",
            message.from_user.id, err,
        )
        return
    parsed = parse_stars_payload(sp.invoice_payload)
    if not parsed:
        return
    plan, period_key, _tg_id, promo = parsed
    await _activate_by_msg(
        message, plan, period_key, "stars",
        invoice_id=sp.invoice_payload,
        provider_charge_id=sp.telegram_payment_charge_id,
        promo=promo,
    )

def referral_reward_plan(current_plan: str, last_paid_plan: str | None) -> str:
    """Keep an active plan, restore the last paid plan, or fall back to Start."""
    if current_plan in ("start", "pro", "business", "trial"):
        return current_plan
    if last_paid_plan in ("start", "pro", "business"):
        return last_paid_plan
    return "start"


def referral_reward_expiry(
    current_expiry: datetime.datetime | None,
    now: datetime.datetime,
    bonus_days: int,
) -> datetime.datetime:
    """Extend a future expiry; otherwise start the reward period now."""
    base = current_expiry if current_expiry and current_expiry > now else now
    return base + datetime.timedelta(days=bonus_days)


async def _notify_referral_reward(referrer) -> None:
    from aiogram import Bot
    from app.config import settings

    lang = normalize_language(referrer.language)
    text = get_text(
        lang, "referral_reward",
        plan=plan_display_name(referrer.plan, lang),
        days=settings.referral_bonus_days,
        date=referrer.plan_expires_at.strftime("%d.%m.%Y"),
    )
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(referrer.telegram_id, text)
    except Exception:
        logger.exception("Failed to notify referrer %d", referrer.id)
    finally:
        await bot.session.close()


async def _apply_referral_bonus(user_id: int) -> None:
    """Activate the referrer's reward once after the referral pays.

    Cap: at most ``settings.max_referrals_per_month`` paid rewards per
    referrer in the current UTC calendar month.
    """
    from app.config import settings
    from app.db.models import Referral, User
    from app.db.session import async_session_factory
    from sqlalchemy import func

    async with async_session_factory() as session:
        referral = (await session.execute(
            select(Referral)
            .where(Referral.referral_id == user_id, Referral.status == "pending")
            .with_for_update()
        )).scalar_one_or_none()
        if not referral:
            return
        referrer = (await session.execute(
            select(User).where(User.id == referral.referrer_id).with_for_update()
        )).scalar_one_or_none()
        if not referrer:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        paid_this_month = (await session.execute(
            select(func.count(Referral.id)).where(
                Referral.referrer_id == referrer.id,
                Referral.status == "paid",
                Referral.activated_at >= month_start,
            )
        )).scalar() or 0
        if paid_this_month >= settings.max_referrals_per_month:
            logger.info(
                "Referral reward skipped: referrer %d hit monthly cap %d",
                referrer.id, settings.max_referrals_per_month,
            )
            referral.status = "capped"
            await session.commit()
            return

        last_paid_plan = (await session.execute(select(Subscription.plan).where(
            Subscription.user_id == referrer.id,
            Subscription.payment_status == "paid",
            Subscription.plan.in_(("start", "pro", "business")),
        ).order_by(Subscription.created_at.desc()).limit(1))).scalar_one_or_none()
        reward_plan = referral_reward_plan(referrer.plan, last_paid_plan)
        if referrer.plan != reward_plan or not referrer.plan_expires_at or referrer.plan_expires_at <= now:
            referrer.plan_activated_at = now
        referrer.plan = reward_plan
        referrer.plan_expires_at = referral_reward_expiry(
            referrer.plan_expires_at, now, settings.referral_bonus_days
        )
        referrer.free_lifecycle_at = None
        referral.status = "paid"
        referral.bonus_days = settings.referral_bonus_days
        referral.referral_trial_bonus = settings.referral_trial_bonus
        referral.activated_at = now
        await session.commit()
    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()
    await _notify_referral_reward(referrer)
    from app.worker.notify_admin import notify_admin
    ref_name = f"@{referrer.username}" if referrer.username else f"ID:{referrer.telegram_id}"
    await notify_admin(
        f"🎁 Реферал оплатил!\n\n👤 Реферер: {ref_name}\n"
        f"🎟 {referrer.plan} · +{settings.referral_bonus_days} дней"
    )

async def maybe_offer_annual(db_user_id: int, telegram_id: int, plan: str, period_key: str, lang: str = "ru"):
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
    text = get_text(lang, "annual_offer", monthly_total=f"{monthly_year:.0f}", plan=plan_display_name(plan, lang), year_total=f"{year['total']:.0f}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text(lang, "annual_offer_btn", total=f"{year['total']:.0f}"), callback_data=f"pay_period:{plan}:1y")]])
    from aiogram import Bot
    bot = Bot(token=settings.bot_token)
    try:
        await bot.send_message(telegram_id, text, reply_markup=kb)
    except Exception:
        logger.exception("Annual upsell send failed for %d", telegram_id)
    finally:
        await bot.session.close()

async def _activate_by_msg(
    message,
    plan,
    period_key,
    method,
    invoice_id,
    *,
    provider_charge_id: str,
    promo: str | None = None,
):
    # Политика (#81): оплата всегда устанавливает оплаченный план и срок 30×months
    # ОТ ТЕКУЩЕГО МОМЕНТА. Повторный charge_id — already_applied без продления.
    info = _calc_winback(plan) if promo == "wb25" else _calc(plan, period_key)
    async for s in get_session():
        u = await get_user(s, message.from_user.id)
        if not u:
            return
        user_db_id = u.id
        lang = normalize_language(getattr(u, "language", None))

    from app.payments.activate import activate_paid_subscription
    try:
        result = await activate_paid_subscription(
            user_db_id=user_db_id,
            plan=plan,
            period_key=period_key,
            method=method,
            provider_charge_id=provider_charge_id,
            invoice_id=invoice_id,
            amount=info["total"],
            promo=promo,
            months=info["months"],
        )
    except ValueError as exc:
        if str(exc) == "winback_offer_inactive":
            logger.warning(
                "Stars activation rejected for user %d: winback offer inactive",
                user_db_id,
            )
            return
        raise
    if not result:
        return

    if result.status == "created":
        from app.cache.subscription_cache import invalidate_all_subscription_caches
        await invalidate_all_subscription_caches()
        await _apply_referral_bonus(user_db_id)
        from app.userbot.discovery import notify_new_subscription
        asyncio.create_task(notify_new_subscription(
            message.from_user.username, message.from_user.id,
            plan, period_key, "direct", info["total"],
        ))
        from app.analytics import record_event, consume_conversion_trigger
        async for s in get_session():
            u = await get_user(s, message.from_user.id)
        trigger = await consume_conversion_trigger(user_db_id)
        await record_event(
            "payment_succeeded", u, trigger=trigger,
            context={"target_plan": plan, "period": period_key, "method": method, "success": True},
        )
        await maybe_offer_annual(user_db_id, message.from_user.id, plan, period_key, lang)

    exp = result.expires_at
    await message.answer(get_text(
        lang, "payment_success",
        plan=plan_display_name(result.plan, lang),
        period=period_display_name(result.period_key, lang),
        date=exp.strftime("%d.%m.%Y"),
    ))

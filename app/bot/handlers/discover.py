"""Settings, language, about, referral, instructions — misc handlers."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.db.crud import get_user
from app.db.session import get_session
from app.locales import get_text

router = Router()


async def _get_lang(callback: CallbackQuery) -> str:
    """Get user language from DB."""
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        return user.language if user else "ru"


@router.callback_query(F.data == "menu:language")
async def on_language(callback: CallbackQuery):
    lang = await _get_lang(callback)
    text = "Выбери язык / Choose language:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def on_settings(callback: CallbackQuery):
    lang = await _get_lang(callback)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_keywords"), callback_data="menu:keywords")],
        [InlineKeyboardButton(text=get_text(lang, "btn_channels"), callback_data="menu:channels")],
        [InlineKeyboardButton(text=get_text(lang, "btn_subscriptions"), callback_data="menu:subs")],
        [InlineKeyboardButton(text=get_text(lang, "btn_stats"), callback_data="menu:stats")],
        [InlineKeyboardButton(text=get_text(lang, "btn_csv"), callback_data="menu:csv")],
        [InlineKeyboardButton(text=get_text(lang, "btn_digest"), callback_data="menu:digest")],
        [InlineKeyboardButton(text=get_text(lang, "btn_language"), callback_data="menu:language")],
        [InlineKeyboardButton(text=get_text(lang, "btn_instructions"), callback_data="menu:instructions")],
        [InlineKeyboardButton(text=get_text(lang, "btn_about"), callback_data="menu:about")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(get_text(lang, "settings_title"), reply_markup=kb)
    await callback.answer()


async def build_stats_screen(user, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """Экран статистики (T5.1): Free/Старт → пейволл; Профи — 7 дн.; Бизнес/Trial — 30 дн. + по направлениям."""
    from app.bot.handlers.plan import paywall_screen
    from app.db.crud import get_daily_lead_counts, get_user_subscriptions
    from app.cache.subscription_cache import get_segment_stats

    plan = user.plan if user else "free"
    if plan in ("free", "start"):
        return await paywall_screen("stats", plan, lang)

    full = plan in ("business", "trial")
    days = 30 if full else 7
    async for s in get_session():
        by_day = await get_daily_lead_counts(s, user.id, days)
        seg_totals, seg_names = {}, {}
        if full:
            subs = await get_user_subscriptions(s, user.id)
            seg_ids = list({sub.segment_id for sub in subs})
            seg_totals = await get_segment_stats(user.id, seg_ids, days)
            from app.db.models import Segment
            from sqlalchemy import select as sa_sel
            for seg in (await s.execute(sa_sel(Segment).where(Segment.id.in_(seg_ids)))).scalars() if seg_ids else []:
                seg_names[seg.id] = f"{seg.emoji or ''} {seg.title_ru if lang == 'ru' else (seg.title_en or seg.title_ru)}".strip()

    total = sum(by_day.values())
    text = f"{get_text(lang, 'stats_title')}\n\n{get_text(lang, 'stats_period', days=days, total=total)}\n"
    if total == 0:
        text += f"\n{get_text(lang, 'stats_empty')}"
    else:
        text += f"\n{get_text(lang, 'stats_byday_header')}\n"
        for d in sorted(by_day, reverse=True)[:7]:
            text += f"{d[5:]} — {by_day[d]}\n"
        nonzero = [(sid, n) for sid, n in seg_totals.items() if n]
        if full and nonzero:
            text += f"\n{get_text(lang, 'stats_byseg_header')}\n"
            for sid, n in sorted(nonzero, key=lambda x: -x[1]):
                text += f"{seg_names.get(sid, f'#{sid}')} — {n}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:settings")]])
    return text, kb


@router.callback_query(F.data == "menu:stats")
async def on_stats(callback: CallbackQuery):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        lang = user.language if user else "ru"
    text, kb = await build_stats_screen(user, lang)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


def _digest_kb(lang: str, current: str) -> InlineKeyboardMarkup:
    """Экран выбора режима доставки (T5.3) — текущий отмечен точкой."""
    rows = []
    for mode in ("instant", "hourly", "daily2"):
        mark = "🔘 " if mode == current else "⚪ "
        rows.append([InlineKeyboardButton(
            text=mark + get_text(lang, f"digest_{mode}"), callback_data=f"digest:{mode}")])
    rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:digest")
async def on_digest_menu(callback: CallbackQuery):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        lang = user.language if user else "ru"
        current = user.digest_mode if user else "instant"
    await callback.message.edit_text(get_text(lang, "digest_title"), reply_markup=_digest_kb(lang, current))
    await callback.answer()


@router.callback_query(F.data.startswith("digest:"))
async def on_digest_set(callback: CallbackQuery):
    mode = callback.data.split(":")[1]
    if mode not in ("instant", "hourly", "daily2"):
        await callback.answer()
        return
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        lang = user.language if user else "ru"
        if user:
            user.digest_mode = mode
            await session.commit()
    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()  # digest_mode едет в кэше подписок
    await callback.message.edit_text(get_text(lang, "digest_title"), reply_markup=_digest_kb(lang, mode))
    await callback.answer(get_text(lang, "digest_saved"))


def _build_csv(rows) -> str:
    """CSV из строк sent_log (T5.2): метаданные, без текста заявки."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "chat", "segment", "sender", "link", "urgent"])
    for r in rows:
        link = (f"https://t.me/{r.chat_username}/{r.message_id}"
                if r.chat_username and r.message_id else "")
        w.writerow([
            r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
            r.chat_username or "", r.segment or "",
            f"@{r.sender}" if r.sender else "", link,
            "1" if r.is_urgent else "",
        ])
    return buf.getvalue()


@router.callback_query(F.data == "menu:csv")
async def on_csv_export(callback: CallbackQuery):
    from aiogram.types import BufferedInputFile
    from app.bot.handlers.plan import paywall_screen
    from app.db.crud import get_sent_log_for_export

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        lang = user.language if user else "ru"
        plan = user.plan if user else "free"
        rows = await get_sent_log_for_export(session, user.id, 30) if plan in ("business", "trial") else []

    if plan not in ("business", "trial"):
        text, kb = await paywall_screen("csv", plan, lang)
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
        return

    if not rows:
        await callback.answer(get_text(lang, "csv_empty", days=30), show_alert=True)
        return

    data = _build_csv(rows).encode("utf-8-sig")  # BOM — Excel корректно откроет UTF-8
    doc = BufferedInputFile(data, filename="leadhunter_leads.csv")
    await callback.message.answer_document(
        doc, caption=get_text(lang, "csv_caption", days=30, count=len(rows)))
    await callback.answer()


@router.callback_query(F.data == "menu:instructions")
async def on_instructions(callback: CallbackQuery):
    lang = await _get_lang(callback)
    if lang == "ru":
        text = (
            "📖 <b>Инструкции</b>\n\n"
            "<b>1. Как добавить канал</b>\n"
            "• ⚙️ Настройки → 📢 Мои каналы\n"
            "• «➕ Добавить канал»\n"
            "• Отправьте @username канала\n\n"
            "<b>2. Как добавить ключевые слова</b>\n"
            "• ⚙️ Настройки → ⚙️ Мои ключевые слова\n"
            "• «➕ Добавить слово»\n"
            "• Отправьте фразу: «ищу повара»\n\n"
            "<b>3. Как оплатить через CryptoBot</b>\n"
            "• 💰 Тариф и оплата → выбрать → ₮ CryptoBot\n"
            "• Пополнить USDT: Binance P2P, Bybit, @wallet\n"
            "• Перевести USDT по счёту в @CryptoBot\n"
            "• Тариф активируется автоматически\n\n"
            "<b>4. Как купить USDT с карты</b>\n"
            "• Binance P2P: binance.com → Купить → P2P\n"
            "• Bybit P2P: bybit.com → Купить → P2P\n"
            "• Telegram @wallet: /start → Пополнить → Карта"
        )
    else:
        text = (
            "📖 <b>Instructions</b>\n\n"
            "<b>1. Add a channel</b>\n"
            "• ⚙️ Settings → 📢 My channels\n"
            "• «➕ Add channel»\n"
            "• Send the @username\n\n"
            "<b>2. Add keywords</b>\n"
            "• ⚙️ Settings → ⚙️ My keywords\n"
            "• «➕ Add keyword»\n"
            "• Send a phrase: «looking for a chef»\n\n"
            "<b>3. Pay via CryptoBot</b>\n"
            "• 💰 Plan → choose → ₮ CryptoBot\n"
            "• Top up USDT: Binance P2P, Bybit, @wallet\n"
            "• Send USDT to @CryptoBot invoice\n"
            "• Activates automatically\n\n"
            "<b>4. Buy USDT with card</b>\n"
            "• Binance P2P: binance.com → Buy → P2P\n"
            "• Bybit P2P: bybit.com → Buy → P2P\n"
            "• Telegram @wallet: /start → Top up → Card"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:about")
async def on_about(callback: CallbackQuery):
    lang = await _get_lang(callback)
    from app.db.models import CatalogChannel, Country
    from sqlalchemy import func, select as sa_sel
    from app.db.session import async_session_factory
    async with async_session_factory() as s:
        ch = (await s.execute(sa_sel(func.count(CatalogChannel.id)))).scalar() or 0
        co = (await s.execute(sa_sel(func.count(Country.id)))).scalar() or 0

    if lang == "ru":
        text = (
            f"ℹ️ LeadHunter\n\n"
            f"Пока конкуренты листают чаты вручную,\n"
            f"ты уже отвечаешь клиенту.\n\n"
            f"📊 {ch} каналов в {co} странах\n"
            f"🎯 29 направлений бизнеса\n"
            f"⚡ Заявки за 2 секунды\n"
            f"🤖 AI-фильтр спама\n"
            f"📬 Уведомления без лимита\n"
            f"🔒 Контакты клиентов — на платном тарифе\n"
            f"💬 Ответ в 1 клик\n"
            f"🆓 5 дней Business бесплатно\n\n"
            f"Не жди, пока клиент найдёт конкурента.\n"
            f"Начни получать заявки прямо сейчас.\n"
            f"👇 Жми «Поиск клиентов» в главном меню."
        )
    else:
        text = (
            f"ℹ️ LeadHunter\n\n"
            f"While competitors scroll chats manually,\n"
            f"you're already replying to the client.\n\n"
            f"📊 {ch} channels in {co} countries\n"
            f"🎯 29 business categories\n"
            f"⚡ Leads in 2 seconds\n"
            f"🤖 AI spam filter\n"
            f"📬 Unlimited notifications\n"
            f"🔒 Client contacts — on a paid plan\n"
            f"💬 Reply in 1 click\n"
            f"🆓 5-day Business trial free\n\n"
            f"Don't wait for the client to find a competitor.\n"
            f"Start getting leads right now.\n"
            f"👇 Tap «Find clients» in the main menu."
        )
    search_label = "🔍 Поиск клиентов" if lang == "ru" else "🔍 Find clients"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=search_label, callback_data="menu:search")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:referral")
async def on_referral(callback: CallbackQuery):
    import urllib.parse, uuid
    lang = await _get_lang(callback)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return

        from app.db.models import Referral
        from sqlalchemy import select, func
        ref = (await session.execute(
            select(Referral).where(Referral.referrer_id == user.id)
        )).scalars().first()

        if not ref:
            ref = Referral(
                referrer_id=user.id, referral_id=user.id,
                ref_code=uuid.uuid4().hex[:8].upper(), status="active",
            )
            session.add(ref)
            await session.commit()

        invited = (await session.execute(
            select(func.count(Referral.id)).where(Referral.referrer_id == user.id)
        )).scalar() or 0
        activated = (await session.execute(
            select(func.count(Referral.id)).where(
                Referral.referrer_id == user.id, Referral.status == "paid"
            )
        )).scalar() or 0
        from app.config import settings
        bonus_days = activated * settings.referral_bonus_days
        await session.commit()

    link = f"https://t.me/LeadHunterAiApp_bot?start=ref_{ref.ref_code}"

    if lang == "ru":
        share_msg = (
            "Lead Hunter AI — бот, который мониторит сотни Telegram-каналов "
            "и ловит запросы клиентов по твоей нише. Заявки приходят моментально.\n\n"
            "🎁 По моей ссылке — 8 дней Business бесплатно\n"
            f"{link}"
        )
        text = (
            f"🎁 Пригласи друга\n\n"
            f"+{settings.referral_bonus_days} дней подписки когда друг оплатит.\n"
            f"Друг получит +{settings.referral_trial_bonus} дня к триалу "
            f"(итого {settings.trial_days + settings.referral_trial_bonus}).\n\n"
            f"🔗 {link}\n\n"
            f"📊 Приглашено: {invited} | Активировано: {activated} | +{bonus_days} дн"
        )
    else:
        share_msg = (
            "Lead Hunter AI — a bot that monitors hundreds of Telegram channels "
            "and catches client requests in your niche. Leads arrive instantly.\n\n"
            "🎁 8 days of Business free with my link\n"
            f"{link}"
        )
        text = (
            f"🎁 Invite a friend\n\n"
            f"+{settings.referral_bonus_days} days when they pay.\n"
            f"They get +{settings.referral_trial_bonus} trial days "
            f"({settings.trial_days + settings.referral_trial_bonus} total).\n\n"
            f"🔗 {link}\n\n"
            f"📊 Invited: {invited} | Activated: {activated} | +{bonus_days}d"
        )

    share_url = f"https://t.me/share/url?text={urllib.parse.quote(share_msg)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Отправить другу" if lang == "ru" else "📤 Share with a friend",
            url=share_url,
        )],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

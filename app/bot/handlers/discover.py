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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")],
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
        [InlineKeyboardButton(text=get_text(lang, "btn_language"), callback_data="menu:language")],
        [InlineKeyboardButton(text="📖 Инструкции" if lang == "ru" else "📖 Instructions", callback_data="menu:instructions")],
        [InlineKeyboardButton(text=get_text(lang, "btn_about"), callback_data="menu:about")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text("⚙️ Settings" if lang == "en" else "⚙️ Настройки", reply_markup=kb)
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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")],
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
            f"🔒 Контакты клиентов (Pro/Business)\n"
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
            f"🔒 Client contacts (Pro/Business)\n"
            f"💬 Reply in 1 click\n"
            f"🆓 5-day Business trial free\n\n"
            f"Don't wait for the client to find a competitor.\n"
            f"Start getting leads right now.\n"
            f"👇 Tap «Find clients» in the main menu."
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")],
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
            await callback.answer("Error", show_alert=True)
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
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

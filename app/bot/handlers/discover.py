"""Settings, language, about, referral — misc handlers."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.db.crud import get_user
from app.db.session import get_session
from app.locales import get_text

router = Router()


def _user_lang(text: str) -> str:
    if any(w in text.lower() for w in ("русский", "тариф", "настройк", "сервис", "язык", "приглас")):
        return "ru"
    return "en"


@router.callback_query(F.data == "menu:language")
async def on_language(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
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
    lang = _user_lang(callback.message.text or "")
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
    lang = _user_lang(callback.message.text or "")
    if lang == "ru":
        text = (
            "📖 <b>Инструкции</b>\n\n"
            "<b>1. Как добавить канал</b>\n"
            "• Откройте ⚙️ Настройки → 📢 Мои каналы\n"
            "• Нажмите «➕ Добавить канал»\n"
            "• Отправьте @username интересующего канала\n"
            "• Канал появится в вашем списке\n\n"
            "<b>2. Как добавить ключевые слова</b>\n"
            "• Откройте ⚙️ Настройки → ⚙️ Мои ключевые слова\n"
            "• Нажмите «➕ Добавить слово»\n"
            "• Отправьте фразу, например: «ищу повара»\n"
            "• Бот будет присылать уведомления при совпадении\n\n"
            "<b>3. Как оплатить подписку через CryptoBot</b>\n"
            "• Откройте 💰 Тариф и оплата\n"
            "• Выберите тариф и срок\n"
            "• Нажмите «₮ CryptoBot» → «💳 Оплатить»\n"
            "• Пополните баланс USDT через:\n"
            "  – Binance, Bybit, OKX (P2P-покупка с карты)\n"
            "  – @wallet (Telegram-кошелёк)\n"
            "  – Любой криптообменник\n"
            "• Переведите USDT по счёту в @CryptoBot\n"
            "• Тариф активируется <b>автоматически</b>\n\n"
            "<b>4. Как пополнить USDT с карты</b>\n"
            "• Binance P2P: binance.com → Купить крипту → P2P\n"
            "• Bybit P2P: bybit.com → Купить → P2P торговля\n"
            "• Telegram @wallet: /start → Пополнить → Карта\n"
            "• Комиссия: 0-2% в зависимости от продавца"
        )
    else:
        text = (
            "📖 <b>Instructions</b>\n\n"
            "<b>1. How to add a channel</b>\n"
            "• Go to ⚙️ Settings → 📢 My channels\n"
            "• Tap «➕ Add channel»\n"
            "• Send the @username of the channel\n"
            "• The channel will appear in your list\n\n"
            "<b>2. How to add keywords</b>\n"
            "• Go to ⚙️ Settings → ⚙️ My keywords\n"
            "• Tap «➕ Add keyword»\n"
            "• Send a phrase, e.g. «looking for a chef»\n"
            "• The bot will notify you on matches\n\n"
            "<b>3. How to pay via CryptoBot</b>\n"
            "• Go to 💰 Plan & payment\n"
            "• Choose a plan and duration\n"
            "• Tap «₮ CryptoBot» → «💳 Pay»\n"
            "• Top up USDT via:\n"
            "  – Binance, Bybit, OKX (P2P with card)\n"
            "  – @wallet (Telegram wallet)\n"
            "  – Any crypto exchange\n"
            "• Send USDT to the invoice in @CryptoBot\n"
            "• Subscription activates <b>automatically</b>\n\n"
            "<b>4. How to buy USDT with a card</b>\n"
            "• Binance P2P: binance.com → Buy crypto → P2P\n"
            "• Bybit P2P: bybit.com → Buy → P2P trading\n"
            "• Telegram @wallet: /start → Top up → Card\n"
            "• Fee: 0-2% depending on seller"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:settings")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:about")
async def on_about(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")

    # Live stats
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
            f"🔒 Контакты клиентов (на платных тарифах)\n"
            f"💬 Ответ клиенту в 1 клик\n"
            f"🆓 5 дней Business-тарифа бесплатно\n\n"
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
            f"🔒 Client contacts (paid plans)\n"
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
    import urllib.parse
    lang = _user_lang(callback.message.text or "")

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
            import uuid
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
            f"🔥 Нашёл сервис — Lead Hunter AI!\n\n"
            f"Находит клиентов в Telegram: 1747+ каналов в 70 странах, "
            f"AI-фильтр спама, заявки за 2 секунды.\n\n"
            f"🎁 По ссылке — 8 дней Business бесплатно (вместо 5): {link}"
        )
        text = (
            f"🎁 Пригласи друга\n\n"
            f"+{settings.referral_bonus_days} дней подписки когда друг оплатит.\n"
            f"Друг получит +{settings.referral_trial_bonus} дня к триалу (итого {settings.trial_days + settings.referral_trial_bonus}).\n\n"
            f"🔗 {link}\n
"
            f"📊 Приглашено: {invited} | Активировано: {activated} | +{bonus_days} дн"
        )
    else:
        share_msg = (
            f"🔥 Found a tool — Lead Hunter AI!\n\n"
            f"Finds clients on Telegram: 1747+ channels in 70 countries, "
            f"AI spam filter, 2-second leads.\n\n"
            f"🎁 8 days Business free (instead of 5): {link}"
        )
        text = (
            f"🎁 Invite a friend\n\n"
            f"+{settings.referral_bonus_days} days when they pay.\n"
            f"They get +{settings.referral_trial_bonus} trial days ({settings.trial_days + settings.referral_trial_bonus} total).\n\n"
            f"🔗 {link}\n
"
            f"📊 Invited: {invited} | Activated: {activated} | +{bonus_days}d"
        )

    share_url = f"https://t.me/share/url?url={urllib.parse.quote(link)}&text={urllib.parse.quote(share_msg)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📤 Отправить другу" if lang == "ru" else "📤 Share with a friend",
            url=share_url,
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()
@router.callback_query(F.data == "ref_copy")
async def on_ref_copy(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
    await callback.answer("✅ Ссылка скопирована" if lang == "ru" else "✅ Link copied", show_alert=True)

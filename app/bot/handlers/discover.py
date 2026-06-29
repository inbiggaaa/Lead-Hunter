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
        [InlineKeyboardButton(text=get_text(lang, "btn_about"), callback_data="menu:about")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text("⚙️ Settings" if lang == "en" else "⚙️ Настройки", reply_markup=kb)
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
    lang = _user_lang(callback.message.text or "")
    text = (
        f"🎁 Пригласи друга\n\n"
        f"Пригласи друга в LeadHunter и получи +7 дней подписки,\n"
        f"когда он оплатит Pro или Business.\n\n"
        f"Твой друг получит +3 дня к пробному периоду.\n\n"
        f"Реферальная программа появится позже."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

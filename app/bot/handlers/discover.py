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
    text = (
        f"ℹ️ LeadHunter\n\n"
        f"Система мониторинга заявок в Telegram.\n"
        f"Версия: 0.3.0\n"
        f"Фаза: 7"
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

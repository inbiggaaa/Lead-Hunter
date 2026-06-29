"""Plan, payment, about, settings, language, referral stubs."""

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


# ── Plan & payment ──

@router.callback_query(F.data == "menu:plan")
async def on_plan(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        plan = user.plan if user else "free"

    text = f"💰 {get_text(lang, 'btn_plan')}\n\n"
    text += f"Твой тариф: {plan.capitalize()}\n\n"
    text += "🚀 Pro — $5/мес\n"
    text += "💎 Business — $15/мес\n\n"
    text += "Оплата появится в Фазе 7."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Language ──

@router.callback_query(F.data == "menu:language")
async def on_language(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
    text = "Выбери язык / Choose language:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Settings ──

@router.callback_query(F.data == "menu:settings")
async def on_settings(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
    text = (
        f"⚙️ {get_text(lang, 'btn_settings')}\n\n"
        f"• Дайджест уведомлений: скоро\n"
        f"• Игнор-лист: скоро\n"
        f"• CSV-экспорт: скоро (Business)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── About ──

@router.callback_query(F.data == "menu:about")
async def on_about(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
    text = (
        f"ℹ️ {get_text(lang, 'btn_about')}\n\n"
        f"LeadHunter — система мониторинга заявок в Telegram.\n"
        f"Версия: 0.2.0\n"
        f"Фаза: 3"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Referral ──

@router.callback_query(F.data == "menu:referral")
async def on_referral(callback: CallbackQuery):
    lang = _user_lang(callback.message.text or "")
    text = (
        f"🎁 Пригласи друга\n\n"
        f"Пригласи друга в LeadHunter и получи +7 дней подписки,\n"
        f"когда он оплатит Pro или Business.\n\n"
        f"Твой друг получит +3 дня к пробному периоду.\n\n"
        f"Реферальная программа появится в Фазе 7."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from app.db.crud import get_or_create_user, set_language, set_onboarded
from app.db.session import get_session
from app.locales import get_text

router = Router()


# ── /start ──

@router.message(CommandStart())
async def cmd_start(message: Message):
    async for session in get_session():
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        lang = user.language

        if not user.onboarded:
            await _show_welcome(message, lang)
        else:
            await _show_menu(message, lang)

        await session.commit()


# ── Welcome screen (language selection) ──

async def _show_welcome(message: Message, lang: str):
    text = (
        f"{get_text(lang, 'welcome_title')}\n\n"
        f"{get_text(lang, 'welcome_body')}\n\n"
        f"{get_text(lang, 'welcome_lang_prompt')}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_text(lang, "btn_ru"), callback_data="lang:ru"),
                InlineKeyboardButton(text=get_text(lang, "btn_en"), callback_data="lang:en"),
            ]
        ]
    )
    await message.answer(text, reply_markup=kb)


# ── Language selection ──

@router.callback_query(F.data.startswith("lang:"))
async def on_language_select(callback: CallbackQuery):
    lang = callback.data.split(":")[1]

    async for session in get_session():
        await set_language(session, callback.from_user.id, lang)
        await session.commit()

    await callback.message.edit_text(get_text(lang, "language_set"))
    await _show_onboarding_step1(callback.message, lang)
    await callback.answer()


# ── Onboarding step 1: choose category ──

async def _show_onboarding_step1(message: Message, lang: str):
    text = get_text(lang, "onb_step1_title")
    # Placeholder categories — will be replaced in Phase 3
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🍜 Кейтеринг / Catering", callback_data="onb:cat:catering")],
            [InlineKeyboardButton(text="💆 Массаж / Massage", callback_data="onb:cat:massage")],
            [InlineKeyboardButton(text="🏍 Аренда байков / Bike rental", callback_data="onb:cat:bikes")],
            [
                InlineKeyboardButton(text=get_text(lang, "onb_skip"), callback_data="onb:skip"),
            ],
        ]
    )
    # Use answer() for onboarding messages to avoid edit failures
    await message.answer(text, reply_markup=kb)


# ── Onboarding category select → step 2 ──

@router.callback_query(F.data.startswith("onb:cat:"))
async def on_onboard_category(callback: CallbackQuery):
    lang = _detect_lang_from_message(callback.message)

    # Step 2: country
    text = get_text(lang, "onb_step2_title")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇻🇳 Вьетнам / Vietnam", callback_data="onb:country:vn")],
            [InlineKeyboardButton(text="🇮🇩 Индонезия / Indonesia", callback_data="onb:country:id")],
            [InlineKeyboardButton(text="🇹🇭 Таиланд / Thailand", callback_data="onb:country:th")],
            [
                InlineKeyboardButton(text=get_text(lang, "onb_skip"), callback_data="onb:skip"),
            ],
        ]
    )
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Onboarding skip → finish ──

@router.callback_query(F.data == "onb:skip")
async def on_onboard_skip(callback: CallbackQuery):
    lang = _detect_lang_from_message(callback.message)
    await _finish_onboarding(callback, lang)


# ── Onboarding country select → finish ──

@router.callback_query(F.data.startswith("onb:country:"))
async def on_onboard_country(callback: CallbackQuery):
    lang = _detect_lang_from_message(callback.message)
    await _finish_onboarding(callback, lang)


# ── Onboarding finish → main menu ──

async def _finish_onboarding(callback: CallbackQuery, lang: str):
    async for session in get_session():
        await set_onboarded(session, callback.from_user.id)
        await session.commit()

    text = get_text(lang, "onb_step3_title") + "\n\n" + get_text(lang, "onb_step3_placeholder")
    await callback.message.edit_text(text)

    # Show main menu after a short delay (new message)
    await _show_menu(callback.message, lang)
    await callback.answer()


# ── Main menu ──

async def _show_menu(message: Message, lang: str):
    text = (
        f"{get_text(lang, 'menu_header')}\n\n"
        f"{get_text(lang, 'menu_plan', plan='Free')}\n"
        f"{get_text(lang, 'menu_notifications', sent=0, limit=50)}\n"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "btn_search"), callback_data="menu:search")],
            [InlineKeyboardButton(text=get_text(lang, "btn_keywords"), callback_data="menu:keywords")],
            [InlineKeyboardButton(text=get_text(lang, "btn_channels"), callback_data="menu:channels")],
            [InlineKeyboardButton(text=get_text(lang, "btn_subscriptions"), callback_data="menu:subs")],
            [InlineKeyboardButton(text=get_text(lang, "btn_referral"), callback_data="menu:referral")],
            [InlineKeyboardButton(text=get_text(lang, "btn_plan"), callback_data="menu:plan")],
            [InlineKeyboardButton(text=get_text(lang, "btn_language"), callback_data="menu:language")],
            [InlineKeyboardButton(text=get_text(lang, "btn_settings"), callback_data="menu:settings")],
            [InlineKeyboardButton(text=get_text(lang, "btn_about"), callback_data="menu:about")],
        ]
    )
    await message.answer(text, reply_markup=kb)


# ── Menu stub callbacks ──

@router.callback_query(F.data.startswith("menu:"))
async def on_menu_stub(callback: CallbackQuery):
    lang = _detect_lang_from_message(callback.message)
    await callback.answer(get_text(lang, "coming_soon"), show_alert=True)


# ── Helpers ──

def _detect_lang_from_message(message: Message) -> str:
    """Detect language from message text — simple heuristic."""
    text = message.text or message.caption or ""
    if "Русский" in text or "русский" in text.lower() or "Выбери" in text:
        return "ru"
    return "en"

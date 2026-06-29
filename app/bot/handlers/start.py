from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
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
            await _show_menu_from_db(message, message.from_user.id)

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
        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        is_onboarded = user.onboarded
        await session.commit()

    await callback.message.edit_text(get_text(lang, "language_set"))

    if not is_onboarded:
        await _show_onboarding_step1(callback.message, lang)
    else:
        await _show_menu_from_db(callback.message, callback.from_user.id)
    await callback.answer()


# ── Onboarding step 1: choose category (with language in callback) ──

async def _show_onboarding_step1(message: Message, lang: str):
    # Auto-activate trial and go to main menu — full flow via 🔍 Search
    import datetime
    async for session in get_session():
        await set_onboarded(session, message.chat.id)
        from app.db.crud import get_user as crud_user
        from app.config import settings
        user = await crud_user(session, message.chat.id)
        if user and user.plan == "free":
            now = datetime.datetime.now(datetime.timezone.utc)
            user.plan = "trial"
            user.plan_activated_at = now
            user.plan_expires_at = now + datetime.timedelta(days=settings.trial_days)
        await session.commit()
    await _show_menu_from_db(message, message.chat.id)


# ── Onboarding category select → step 2 ──

@router.callback_query(F.data.startswith("onb:cat:"))
async def on_onboard_category(callback: CallbackQuery):
    parts = callback.data.split(":")
    lang = parts[3] if len(parts) > 3 else "ru"

    # Load all countries from DB
    from app.db.session import async_session_factory
    from app.db.models import Country
    from sqlalchemy import select
    from app.bot.handlers.catalog_nav import _country_flag

    async with async_session_factory() as session:
        result = await session.execute(
            select(Country).where(Country.is_active == True).order_by(Country.name_ru)
        )
        countries = result.scalars().all()

    text = get_text(lang, "onb_step2_title")
    kb_rows = []
    row = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        row.append(InlineKeyboardButton(
            text=f"{flag} {name}",
            callback_data=f"onb:country:{c.slug}:{lang}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    kb_rows.append([
        InlineKeyboardButton(text=get_text(lang, "onb_skip"), callback_data=f"onb:skip:{lang}"),
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Onboarding skip → finish ──

@router.callback_query(F.data.startswith("onb:skip"))
async def on_onboard_skip(callback: CallbackQuery):
    parts = callback.data.split(":")
    lang = parts[1] if len(parts) > 1 else "ru"
    await _finish_onboarding(callback, lang)


# ── Onboarding country select → finish ──

@router.callback_query(F.data.startswith("onb:country:"))
async def on_onboard_country(callback: CallbackQuery):
    parts = callback.data.split(":")
    lang = parts[3] if len(parts) > 3 else "ru"
    await _finish_onboarding(callback, lang)


# ── Onboarding finish → main menu ──

async def _finish_onboarding(callback: CallbackQuery, lang: str):
    import datetime
    async for session in get_session():
        await set_onboarded(session, callback.from_user.id)
        # Activate trial for first-time users
        from app.db.crud import get_user
        from app.config import settings
        user = await get_user(session, callback.from_user.id)
        if user and user.plan == "free":
            now = datetime.datetime.now(datetime.timezone.utc)
            user.plan = "trial"
            user.plan_activated_at = now
            user.plan_expires_at = now + datetime.timedelta(days=settings.trial_days)
            # Notify admin
            from app.userbot.discovery import notify_new_trial
            asyncio.create_task(notify_new_trial(callback.from_user.username, callback.from_user.id, user.source))
        await session.commit()

    text = get_text(lang, "onb_step3_title") + "\n\n" + get_text(lang, "onb_step3_placeholder")
    await callback.message.edit_text(text)

    # Show main menu after a short delay (new message)
    await _show_menu_from_db(callback.message, callback.from_user.id)
    await callback.answer()


# ── Main menu ──

async def _show_menu_from_db(message: Message, telegram_id: int):
    """Show main menu using language and plan from DB."""
    import datetime
    async for session in get_session():
        from app.db.crud import get_user
        user = await get_user(session, telegram_id)
        lang = user.language if user else "ru"
        plan_name = "Free"
        if user:
            plan_name = user.plan.capitalize()
            if user.plan == "trial" and user.plan_expires_at:
                days_left = (user.plan_expires_at - datetime.datetime.now(datetime.timezone.utc)).days
                plan_name = f"Trial ({max(0, days_left)} дн)"
            elif user.plan in ("pro", "business") and user.plan_expires_at:
                days_left = (user.plan_expires_at - datetime.datetime.now(datetime.timezone.utc)).days
                plan_name = f"{user.plan.capitalize()} ({max(0, days_left)} дн)"
    await _show_menu(message, lang, plan_name)


async def _show_menu(message: Message, lang: str, plan_name: str = "Free"):
    text = (
        f"{get_text(lang, 'menu_header')}\n\n"
        f"{get_text(lang, 'menu_plan', plan=plan_name)}\n"
        f"{get_text(lang, 'menu_notifications', sent=0, limit=50)}\n"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "btn_search"), callback_data="menu:search")],
            [InlineKeyboardButton(text=get_text(lang, "btn_plan"), callback_data="menu:plan")],
            [InlineKeyboardButton(text=get_text(lang, "btn_referral"), callback_data="menu:referral")],
            [InlineKeyboardButton(text=get_text(lang, "btn_settings"), callback_data="menu:settings")],
        ]
    )
    await message.answer(text, reply_markup=kb)


# ── Return to main menu ──

@router.callback_query(F.data == "menu:main")
async def on_menu_main(callback: CallbackQuery):
    await _show_menu_from_db(callback.message, callback.from_user.id)
    await callback.answer()


# ── /cancel ──

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await _show_menu_from_db(message, message.from_user.id)


# ── Command shortcuts → menu callbacks ──

@router.message(Command("search"))
async def cmd_search(message: Message):
    await message.answer("🔍", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти к поиску", callback_data="menu:search")]
    ]))

@router.message(Command("keywords"))
async def cmd_keywords(message: Message):
    await message.answer("⚙️", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои ключевые слова", callback_data="menu:keywords")]
    ]))

@router.message(Command("channels"))
async def cmd_channels(message: Message):
    await message.answer("📢", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои каналы", callback_data="menu:channels")]
    ]))

@router.message(Command("subscriptions"))
async def cmd_subscriptions(message: Message):
    await message.answer("📋", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мои подписки", callback_data="menu:subs")]
    ]))

@router.message(Command("plan"))
async def cmd_plan(message: Message):
    await message.answer("💰", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Тариф и оплата", callback_data="menu:plan")]
    ]))

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer("⚙️", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Настройки", callback_data="menu:settings")]
    ]))


# ── Helpers ──

def _detect_lang_from_message(message: Message) -> str:
    """Detect language from message text — simple heuristic."""
    text = message.text or message.caption or ""
    if "Русский" in text or "русский" in text.lower() or "Выбери" in text:
        return "ru"
    return "en"

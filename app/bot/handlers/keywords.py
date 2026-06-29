"""Keyword management: list, add, delete with plan limits."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.crud import (
    add_keyword,
    count_keywords,
    delete_keyword,
    get_keywords,
    get_max_keywords,
    get_user,
)
from app.db.session import get_session
from app.locales import get_text

router = Router()


class AddKeywordState(StatesGroup):
    waiting_for_text = State()


def _user_lang(message: Message) -> str:
    text = message.text or message.caption or ""
    if any(w in text.lower() for w in ("русский", "выбери", "слов", "ключевы")):
        return "ru"
    return "en"


async def _get_user_lang(telegram_id: int) -> str:
    """Get user language from DB."""
    async for session in get_session():
        from app.db.crud import get_user
        user = await get_user(session, telegram_id)
        return user.language if user else "ru"


# ── Menu entry point ──

@router.callback_query(F.data == "menu:keywords")
async def on_menu_keywords(callback: CallbackQuery):
    lang = await _get_user_lang(callback.from_user.id)
    await show_keywords(callback, lang)


# ── Show keywords list ──

async def show_keywords(callback: CallbackQuery, lang: str):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("User not found", show_alert=True)
            return

        keywords = await get_keywords(session, user.id)
        current = len(keywords)
        max_kw = get_max_keywords(user.plan)

    text = f"⚙️ {get_text(lang, 'btn_keywords')}\n\n"
    if not keywords:
        text += (
            f"У тебя пока нет ключевых слов.\n"
            f"Добавь слово — и я буду присылать уведомления,\n"
            f"когда кто-то использует его в чатах.\n\n"
            f"Осталось: {current} из {max_kw} ({user.plan.capitalize()})"
        )
    else:
        text += f"Твои слова ({current}/{max_kw}):\n\n"
        for kw in keywords:
            regex_mark = " [RegEx]" if kw.is_regex else ""
            text += f"{kw.text}{regex_mark}\n"

    kb_buttons = []
    for kw in keywords:
        kb_buttons.append([
            InlineKeyboardButton(text=f"🗑️ {kw.text[:30]}", callback_data=f"kw:del:{kw.id}")
        ])

    if current < max_kw:
        kb_buttons.append([
            InlineKeyboardButton(text=get_text(lang, "btn_keywords") + " ➕", callback_data="kw:add")
        ])

    kb_buttons.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await callback.message.edit_text(text, reply_markup=kb)
    await session.commit()


# ── Add keyword: prompt ──

@router.callback_query(F.data == "kw:add")
async def on_add_keyword_prompt(callback: CallbackQuery, state: FSMContext):
    lang = await _get_user_lang(callback.from_user.id)
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_keywords(session, user.id)
        max_kw = get_max_keywords(user.plan)

        if current >= max_kw:
            await callback.answer(f"Лимит исчерпан: {current}/{max_kw}", show_alert=True)
            return

    await state.set_state(AddKeywordState.waiting_for_text)
    text = (
        f"Отправь мне ключевое слово или фразу.\n"
        f"Например: «ищу повара», «сниму байк».\n\n"
        f"Осталось: {max_kw - current} из {max_kw} ({user.plan.capitalize()})\n\n"
        f"Отправь /cancel для отмены."
    )
    await callback.message.edit_text(text)
    await callback.answer()


# ── Receive keyword text ──

@router.message(AddKeywordState.waiting_for_text)
async def on_keyword_text(message: Message, state: FSMContext):
    text = message.text.strip()
    lang = await _get_user_lang(message.from_user.id)

    if len(text) < 2:
        await message.answer("Слишком короткое. Попробуй ещё раз или /cancel.")
        return

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка.")
            return

        current = await count_keywords(session, user.id)
        max_kw = get_max_keywords(user.plan)
        if current >= max_kw:
            await message.answer(f"Лимит исчерпан: {current}/{max_kw}")
            await state.clear()
            return

        await add_keyword(session, user.id, text)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ Добавлено: «{text}»")

    # Return to keywords screen via callback-like edit on a new message
    async for session in get_session():
        await show_keywords_via_message(message, lang)
        await session.commit()


async def show_keywords_via_message(message: Message, lang: str):
    """Show keywords list via answer() instead of edit_text()."""
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            return
        keywords = await get_keywords(session, user.id)
        current = len(keywords)
        max_kw = get_max_keywords(user.plan)

    text = f"⚙️ {get_text(lang, 'btn_keywords')}\n\n"
    if keywords:
        text += f"Твои слова ({current}/{max_kw}):\n\n"
        for kw in keywords:
            regex_mark = " [RegEx]" if kw.is_regex else ""
            text += f"{kw.text}{regex_mark}\n"
    else:
        text += f"Пока нет слов. Осталось: {current} из {max_kw}\n"

    kb_buttons = []
    for kw in keywords:
        kb_buttons.append([
            InlineKeyboardButton(text=f"🗑️ {kw.text[:30]}", callback_data=f"kw:del:{kw.id}")
        ])
    if current < max_kw:
        kb_buttons.append([
            InlineKeyboardButton(text="➕ Добавить слово", callback_data="kw:add")
        ])
    kb_buttons.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await message.answer(text, reply_markup=kb)


# ── Delete keyword ──

@router.callback_query(F.data.startswith("kw:del:"))
async def on_delete_keyword(callback: CallbackQuery):
    kw_id = int(callback.data.split(":")[2])
    lang = await _get_user_lang(callback.from_user.id)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return

        deleted = await delete_keyword(session, kw_id, user.id)
        await session.commit()

    if deleted:
        await callback.answer("Удалено")
        await show_keywords(callback, lang)
    else:
        await callback.answer("Не найдено", show_alert=True)

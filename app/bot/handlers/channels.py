"""Channel management: list, add, delete with plan limits + private channel alert."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.crud import (
    add_watched_chat,
    count_watched_chats,
    delete_watched_chat,
    get_max_channels,
    get_user,
    get_watched_chats,
)
from app.db.session import get_session
from app.locales import get_text

router = Router()


class AddChannelState(StatesGroup):
    waiting_for_username = State()


def _user_lang(message: Message) -> str:
    text = message.text or message.caption or ""
    if any(w in text.lower() for w in ("русский", "канал", "добав")):
        return "ru"
    return "en"


async def _get_user_lang(telegram_id: int) -> str:
    """Get user language from DB."""
    async for session in get_session():
        from app.db.crud import get_user
        user = await get_user(session, telegram_id)
        return user.language if user else "ru"


# ── Menu entry point ──

@router.callback_query(F.data == "menu:channels")
async def on_menu_channels(callback: CallbackQuery):
    lang = await _get_user_lang(callback.from_user.id)
    await show_channels(callback, lang)


# ── Show channels list ──

def _channel_label(ch, max_len: int = 40) -> str:
    """Человекочитаемое имя канала: title приоритетнее сырого id.

    Каналы, добавленные напрямую по внутреннему ID (bulk-вставка групп без
    @username), показываются названием; голый «@-100…» — только если названия
    нет совсем.
    """
    is_numeric = ch.chat_username.lstrip("-").isdigit()
    title = (ch.title or "").strip()
    if title:
        label = title if is_numeric else f"{title} (@{ch.chat_username})"
    else:
        label = f"группа {ch.chat_username}" if is_numeric else f"@{ch.chat_username}"
    return label[:max_len]


async def show_channels(callback: CallbackQuery, lang: str):
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        channels = await get_watched_chats(session, user.id)
        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)

    text = f"📢 {get_text(lang, 'btn_channels')}\n\n"
    if not channels:
        text += (
            f"У тебя пока нет своих каналов.\n"
            f"Добавь канал — и я буду отслеживать сообщения\n"
            f"только в нём по твоим ключевым словам.\n\n"
            f"Осталось: {current} из {max_ch} ({user.plan.capitalize()})"
        )
    else:
        text += f"Твои каналы ({current}/{max_ch}):\n\n"
        # 4096-лимит Telegram: названия длиннее сырых id, длинный список режем
        for ch in channels[:60]:
            status = " 🔒" if ch.is_private else ""
            text += f"{_channel_label(ch)}{status}\n"
        if len(channels) > 60:
            text += f"… и ещё {len(channels) - 60} (все — в кнопках ниже)\n"

    kb_buttons = []
    for ch in channels:
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"🗑️ {_channel_label(ch, max_len=25)}",
                callback_data=f"ch:del:{ch.id}",
            )
        ])
    if current < max_ch:
        kb_buttons.append([
            InlineKeyboardButton(text="➕ Добавить канал", callback_data="ch:add")
        ])
    kb_buttons.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await callback.message.edit_text(text, reply_markup=kb)
    await session.commit()


# ── Add channel prompt ──

@router.callback_query(F.data == "ch:add")
async def on_add_channel_prompt(callback: CallbackQuery, state: FSMContext):
    lang = await _get_user_lang(callback.from_user.id)
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)
        if current >= max_ch:
            await callback.answer(f"Лимит исчерпан: {current}/{max_ch}", show_alert=True)
            return

    await state.set_state(AddChannelState.waiting_for_username)
    text = (
        f"Отправь мне @username канала.\n"
        f"Например: @danang_chat\n\n"
        f"Осталось: {max_ch - current} из {max_ch} ({user.plan.capitalize()})\n\n"
        f"/cancel для отмены."
    )
    await callback.message.edit_text(text)
    await callback.answer()


# ── Receive channel username ──

@router.message(AddChannelState.waiting_for_username)
async def on_channel_username(message: Message, state: FSMContext):
    raw = message.text.strip().lstrip("@")
    lang = await _get_user_lang(message.from_user.id)

    if len(raw) < 3:
        await message.answer("Некорректный @username. Попробуй ещё раз или /cancel.")
        return

    # Simulate private channel detection: if username starts with 'private_' or similar
    is_private = raw.startswith("private")

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer("Ошибка.")
            await state.clear()
            return

        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)
        if current >= max_ch:
            await message.answer(f"Лимит исчерпан: {current}/{max_ch}")
            await state.clear()
            return

        await add_watched_chat(session, user.id, raw, is_private=is_private)
        await session.commit()

    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()

    await state.clear()

    if is_private:
        await message.answer(
            f"⏳ @{raw} — канал выглядит приватным.\n"
            f"Заявка отправлена администратору на проверку.\n"
            f"Мы сообщим, когда канал будет одобрен."
        )
    else:
        await message.answer(f"✅ Канал @{raw} добавлен!")

    async for session in get_session():
        await show_channels_via_message(message, lang)
        await session.commit()


async def show_channels_via_message(message: Message, lang: str):
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            return
        channels = await get_watched_chats(session, user.id)
        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)

    text = f"📢 {get_text(lang, 'btn_channels')}\n\n"
    if channels:
        text += f"Твои каналы ({current}/{max_ch}):\n\n"
        # 4096-лимит Telegram: названия длиннее сырых id, длинный список режем
        for ch in channels[:60]:
            status = " 🔒" if ch.is_private else ""
            text += f"{_channel_label(ch)}{status}\n"
        if len(channels) > 60:
            text += f"… и ещё {len(channels) - 60} (все — в кнопках ниже)\n"
    else:
        text += f"Пока нет каналов. Осталось: {current} из {max_ch}\n"

    kb_buttons = []
    for ch in channels:
        kb_buttons.append([
            InlineKeyboardButton(text=f"🗑️ {_channel_label(ch, max_len=25)}", callback_data=f"ch:del:{ch.id}")
        ])
    if current < max_ch:
        kb_buttons.append([
            InlineKeyboardButton(text="➕ Добавить канал", callback_data="ch:add")
        ])
    kb_buttons.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    await message.answer(text, reply_markup=kb)


# ── Delete channel ──

@router.callback_query(F.data.startswith("ch:del:"))
async def on_delete_channel(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[2])
    lang = await _get_user_lang(callback.from_user.id)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        deleted = await delete_watched_chat(session, chat_id, user.id)
        await session.commit()

    if deleted:
        from app.cache.subscription_cache import invalidate_all_subscription_caches
        await invalidate_all_subscription_caches()

    if deleted:
        await callback.answer("Удалено")
        await show_channels(callback, lang)
    else:
        await callback.answer("Не найдено", show_alert=True)

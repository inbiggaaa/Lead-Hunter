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
from app.bot.handlers.plan import plan_display_name, paywall_screen

router = Router()


class AddChannelState(StatesGroup):
    waiting_for_username = State()



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
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return
        channels = await get_watched_chats(session, user.id)
        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)

    text = f"📢 {get_text(lang, 'btn_channels')}\n\n"
    if not channels:
        text += get_text(lang, "list_empty_channels", current=current, limit=max_ch, plan=plan_display_name(user.plan, lang))
    else:
        text += get_text(lang, "channels_title", current=current, limit=max_ch) + "\n\n"
        # 4096-лимит Telegram: названия длиннее сырых id, длинный список режем
        for ch in channels[:60]:
            status = " 🔒" if ch.is_private else ""
            text += f"{_channel_label(ch)}{status}\n"
        if len(channels) > 60:
            text += get_text(lang, "more_items", count=len(channels)-60) + "\n"

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
            InlineKeyboardButton(text=get_text(lang, "btn_add_channel"), callback_data="ch:add")
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
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return
        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)
        if current >= max_ch:
            pw_text, pw_kb = await paywall_screen("channel", user.plan, lang, user)
            await callback.message.edit_text(pw_text, reply_markup=pw_kb)
            await callback.answer()
            return

    await state.set_state(AddChannelState.waiting_for_username)
    text = get_text(lang, "channels_prompt", remaining=max_ch-current, limit=max_ch, plan=plan_display_name(user.plan, lang))
    await callback.message.edit_text(text)
    await callback.answer()


# ── Receive channel username ──

@router.message(AddChannelState.waiting_for_username)
async def on_channel_username(message: Message, state: FSMContext):
    raw = message.text.strip().lstrip("@")
    lang = await _get_user_lang(message.from_user.id)

    if len(raw) < 3:
        await message.answer(get_text(lang, "channel_invalid"))
        return

    # Simulate private channel detection: if username starts with 'private_' or similar
    is_private = raw.startswith("private")

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer(get_text(lang, "error_generic"))
            await state.clear()
            return

        current = await count_watched_chats(session, user.id)
        max_ch = get_max_channels(user.plan)
        if current >= max_ch:
            pw_text, pw_kb = await paywall_screen("channel", user.plan, lang, user)
            await message.answer(pw_text, reply_markup=pw_kb)
            await state.clear()
            return

        await add_watched_chat(session, user.id, raw, is_private=is_private)
        await session.commit()

    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()

    await state.clear()

    if is_private:
        await message.answer(get_text(lang, "channel_private_pending", channel=raw))
    else:
        await message.answer(get_text(lang, "item_added", item=f""))

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
        text += get_text(lang, "channels_title", current=current, limit=max_ch) + "\n\n"
        # 4096-лимит Telegram: названия длиннее сырых id, длинный список режем
        for ch in channels[:60]:
            status = " 🔒" if ch.is_private else ""
            text += f"{_channel_label(ch)}{status}\n"
        if len(channels) > 60:
            text += get_text(lang, "more_items", count=len(channels)-60) + "\n"
    else:
        text += get_text(lang, "list_empty_channels", current=current, limit=max_ch, plan=plan_display_name(user.plan, lang))

    kb_buttons = []
    for ch in channels:
        kb_buttons.append([
            InlineKeyboardButton(text=f"🗑️ {_channel_label(ch, max_len=25)}", callback_data=f"ch:del:{ch.id}")
        ])
    if current < max_ch:
        kb_buttons.append([
            InlineKeyboardButton(text=get_text(lang, "btn_add_channel"), callback_data="ch:add")
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
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return
        deleted = await delete_watched_chat(session, chat_id, user.id)
        await session.commit()

    if deleted:
        from app.cache.subscription_cache import invalidate_all_subscription_caches
        await invalidate_all_subscription_caches()

    if deleted:
        await callback.answer(get_text(lang, "item_deleted"))
        await show_channels(callback, lang)
    else:
        await callback.answer(get_text(lang, "item_not_found"), show_alert=True)

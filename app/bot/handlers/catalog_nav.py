"""FSM catalog navigation: segment → country → geo → cities → confirm → trial/payment."""

import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select, func

from app.db.crud import (
    count_user_subscriptions,
    create_subscription,
    get_countries,
    get_cities,
    get_max_segments,
    get_segments,
    get_user,
    get_user_subscriptions,
    delete_subscription,
)
from app.db.session import get_session
from app.locales import get_text

router = Router()


class CatStates(StatesGroup):
    choosing_segment = State()
    choosing_country = State()
    choosing_geo = State()
    choosing_cities = State()
    confirm_subscription = State()


def _user_lang(message: Message) -> str:
    text = message.text or message.caption or ""
    if any(w in text.lower() for w in ("русский", "выбери", "направлен", "стран", "город", "подписк")):
        return "ru"
    return "en"


# ── Step 1: Choose segment ──

@router.callback_query(F.data == "menu:search")
async def on_search_start(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    await state.clear()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        segments = await get_segments(session)

    text = f"Чем ты занимаешься? Выбери направление:\n\nПодписки: {current}/{max_seg}"

    kb_rows = []
    for seg in segments:
        emoji = seg.emoji or ""
        title = seg.title_ru if lang == "ru" else (seg.title_en or seg.title_ru)
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {title}",
                callback_data=f"cat:seg:{seg.id}",
            )
        ])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_segment)
    await state.update_data(lang=lang)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Step 2: Choose country ──

@router.callback_query(CatStates.choosing_segment, F.data.startswith("cat:seg:"))
async def on_segment_chosen(callback: CallbackQuery, state: FSMContext):
    segment_id = int(callback.data.split(":")[2])
    lang = _user_lang(callback.message)

    await state.update_data(segment_id=segment_id)

    async for session in get_session():
        countries = await get_countries(session)

    text = "В какой стране ищешь клиентов?"

    kb_rows = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        kb_rows.append([
            InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"cat:country:{c.id}")
        ])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:search")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_country)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Step 3: Choose geo mode ──

@router.callback_query(CatStates.choosing_country, F.data.startswith("cat:country:"))
async def on_country_chosen(callback: CallbackQuery, state: FSMContext):
    country_id = int(callback.data.split(":")[2])
    lang = _user_lang(callback.message)

    await state.update_data(country_id=country_id)

    text = "Где именно ищешь?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 По всей стране", callback_data="cat:geo:all")],
        [InlineKeyboardButton(text="🏙 В городах", callback_data="cat:geo:cities")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:search")],
    ])

    await state.set_state(CatStates.choosing_geo)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Step 4a: Cities selection ──

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:cities")
async def on_geo_cities(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    data = await state.get_data()
    country_id = data["country_id"]

    async for session in get_session():
        cities = await get_cities(session, country_id)

    text = "Выбери города:"
    kb_rows = []
    selected_cities: list[int] = data.get("selected_cities", [])

    for city in cities:
        name = city.name_ru if lang == "ru" else (city.name_en or city.name_ru)
        prefix = "✅ " if city.id in selected_cities else ""
        kb_rows.append([
            InlineKeyboardButton(
                text=f"{prefix}{name}",
                callback_data=f"cat:city:{city.id}",
            )
        ])
    kb_rows.append([InlineKeyboardButton(text="✅ Готово", callback_data="cat:confirm")])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:country")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_cities)
    await state.update_data(selected_cities=selected_cities)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Toggle city selection ──

@router.callback_query(CatStates.choosing_cities, F.data.startswith("cat:city:"))
async def on_toggle_city(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    selected: list[int] = data.get("selected_cities", [])

    if city_id in selected:
        selected.remove(city_id)
    else:
        selected.append(city_id)

    await state.update_data(selected_cities=selected)
    await on_geo_cities(callback, state)


# ── Back to country from cities ──

@router.callback_query(CatStates.choosing_cities, F.data == "cat:back:country")
async def on_back_to_country(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    data = await state.get_data()

    async for session in get_session():
        countries = await get_countries(session)

    text = "В какой стране ищешь клиентов?"
    kb_rows = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        kb_rows.append([
            InlineKeyboardButton(text=f"{flag} {name}", callback_data=f"cat:country:{c.id}")
        ])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:search")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_country)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Step 4b/5: Confirm subscription ──

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:all")
async def on_geo_all(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    data = await state.get_data()
    await state.update_data(mode="all", selected_cities=[])
    await _show_confirmation(callback, state)


@router.callback_query(CatStates.choosing_cities, F.data == "cat:confirm")
async def on_confirm_from_cities(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[int] = data.get("selected_cities", [])
    if not selected:
        await callback.answer("Выбери хотя бы один город", show_alert=True)
        return
    await state.update_data(mode="cities")

    await _show_confirmation(callback, state)


async def _show_confirmation(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    data = await state.get_data()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)

    if current >= max_seg:
        await callback.answer(f"Лимит подписок исчерпан: {current}/{max_seg}", show_alert=True)
        return

    # Check for duplicate subscription
    async for session in get_session():
        existing = await get_user_subscriptions(session, user.id)
    duplicate = any(
        sub.segment_id == data["segment_id"] and sub.country_id == data["country_id"]
        for sub in existing
    )

    if duplicate:
        await callback.answer("Уже подписан на это направление в этой стране", show_alert=True)
        return

    text = "Подтверди подписку:\n\n"
    text += f"📌 Направление: #{data['segment_id']}\n"
    text += f"🌍 Страна: #{data['country_id']}\n"
    if data.get("mode") == "cities":
        text += f"🏙 Города: {len(data.get('selected_cities', []))}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="cat:subscribe")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="cat:back:from_confirm")],
    ])

    await state.set_state(CatStates.confirm_subscription)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Execute subscription ──

@router.callback_query(CatStates.confirm_subscription, F.data == "cat:subscribe")
async def on_subscribe(callback: CallbackQuery, state: FSMContext):
    lang = _user_lang(callback.message)
    data = await state.get_data()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return

        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        if current >= max_seg:
            await callback.answer(f"Лимит: {current}/{max_seg}", show_alert=True)
            return

        await create_subscription(
            session,
            user_id=user.id,
            segment_id=data["segment_id"],
            country_id=data["country_id"],
            mode=data.get("mode", "all"),
            city_ids=data.get("selected_cities"),
        )

        # Activate trial if this is the user's first subscription
        is_first = current == 0
        if is_first and user.plan == "free":
            from app.config import settings
            user.plan = "trial"
            user.plan_activated_at = datetime.datetime.now(datetime.timezone.utc)
            user.plan_expires_at = user.plan_activated_at + datetime.timedelta(days=settings.trial_days)

        await session.commit()

    await state.clear()

    if is_first:
        text = (
            f"🎉 Готово! Ты получил 5 дней Business-тарифа.\n"
            f"Вот твои первые заявки:\n\n"
            f"(Заявки появятся в Фазе 5)"
        )
    else:
        text = "✅ Подписка добавлена!"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ── Subscriptions list (from menu) ──

@router.callback_query(F.data == "menu:subs")
async def on_show_subscriptions(callback: CallbackQuery):
    lang = _user_lang(callback.message)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        subs = await get_user_subscriptions(session, user.id)
        current = len(subs)
        max_seg = get_max_segments(user.plan)

    text = f"📋 Мои подписки ({current}/{max_seg})\n\n"
    if not subs:
        text += "У тебя пока нет подписок.\nНажми 🔍 Поиск клиентов чтобы найти первых!"

    kb_rows = []
    for sub in subs:
        kb_rows.append([
            InlineKeyboardButton(
                text=f"🗑️ Сегмент #{sub.segment_id} / Страна #{sub.country_id}",
                callback_data=f"sub:del:{sub.id}",
            )
        ])
    kb_rows.append([InlineKeyboardButton(text="🔍 Поиск клиентов", callback_data="menu:search")])
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("sub:del:"))
async def on_delete_subscription(callback: CallbackQuery):
    sub_id = int(callback.data.split(":")[2])
    lang = _user_lang(callback.message)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        await delete_subscription(session, sub_id, user.id)
        await session.commit()

    await callback.answer("Отписано")
    await on_show_subscriptions(callback)


# ── Back handlers ──

@router.callback_query(CatStates.choosing_country, F.data == "menu:search")
async def on_back_to_segments(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await on_search_start(callback, state)


@router.callback_query(CatStates.confirm_subscription, F.data == "cat:back:from_confirm")
async def on_back_from_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await on_search_start(callback, state)


# ── Helpers ──

def _country_flag(slug: str) -> str:
    flags = {
        "vn": "🇻🇳", "id": "🇮🇩", "th": "🇹🇭", "ru": "🇷🇺", "other": "🌍",
    }
    return flags.get(slug, "🌍")

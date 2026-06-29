"""FSM catalog navigation: segments (multi) → country → geo → cities (multi) → confirm."""

import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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
    choosing_segments = State()
    choosing_country = State()
    choosing_geo = State()
    choosing_cities = State()
    confirm_subscription = State()


# ── Language helpers ──

async def _get_lang(callback: CallbackQuery, state: FSMContext) -> str:
    data = await state.get_data()
    lang = data.get("lang")
    if lang:
        return lang
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        return user.language if user else "ru"


async def _get_lang_nostate(callback: CallbackQuery) -> str:
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        return user.language if user else "ru"


def _country_flag(slug: str) -> str:
    flags = {"vn": "🇻🇳", "id": "🇮🇩", "th": "🇹🇭", "ru": "🇷🇺", "other": "🌍",
             "tr": "🇹🇷", "ae": "🇦🇪", "ge": "🇬🇪", "kz": "🇰🇿", "de": "🇩🇪",
             "es": "🇪🇸", "fr": "🇫🇷", "us": "🇺🇸", "gb": "🇬🇧", "in": "🇮🇳",
             "cn": "🇨🇳", "jp": "🇯🇵", "br": "🇧🇷", "eg": "🇪🇬", "za": "🇿🇦"}
    return flags.get(slug, "🌍")


# ═══════════════ STEP 1: Choose segments (multi-select) ═══════════════

@router.callback_query(F.data == "menu:search")
async def on_search_start(callback: CallbackQuery, state: FSMContext):
    lang = await _get_lang_nostate(callback)
    await state.clear()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        segments = await get_segments(session)

    selected: list[int] = []
    await state.update_data(lang=lang, plan=user.plan, max_seg=max_seg, current_subs=current)

    text = f"Выбери направления ({current}/{max_seg}):\n\n"
    text += "Можно выбрать несколько. Нажми «Готово» когда закончишь."

    await _render_segments(callback, state, segments, selected, lang, current, max_seg)
    await state.set_state(CatStates.choosing_segments)
    await callback.answer()


async def _render_segments(
    callback: CallbackQuery, state: FSMContext,
    segments, selected: list[int], lang: str,
    current: int, max_seg: int,
):
    kb_rows = []
    for seg in segments:
        emoji = seg.emoji or ""
        title = seg.title_ru if lang == "ru" else (seg.title_en or seg.title_ru)
        prefix = "☑️ " if seg.id in selected else "⬜ "
        kb_rows.append([InlineKeyboardButton(
            text=f"{prefix}{emoji} {title}",
            callback_data=f"cat:seg:{seg.id}",
        )])

    # "Done" button — enabled only if at least 1 selected
    if selected and (current + len(selected) <= max_seg):
        kb_rows.append([InlineKeyboardButton(
            text=f"✅ Готово ({len(selected)} выбрано)",
            callback_data="cat:segs_done",
        )])

    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(
        f"Выбери направления ({current + len(selected)}/{max_seg}):\n\n"
        f"Можно выбрать несколько. Нажми «Готово» когда закончишь.",
        reply_markup=kb,
    )


@router.callback_query(CatStates.choosing_segments, F.data.startswith("cat:seg:"))
async def on_toggle_segment(callback: CallbackQuery, state: FSMContext):
    seg_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    selected: list[int] = data.get("selected_segments", [])
    max_seg = data.get("max_seg", 1)
    current = data.get("current_subs", 0)
    lang = data.get("lang", "ru")

    if seg_id in selected:
        selected.remove(seg_id)
    else:
        if current + len(selected) >= max_seg:
            await callback.answer(f"Лимит: {max_seg} направлений", show_alert=True)
            return
        selected.append(seg_id)

    await state.update_data(selected_segments=selected)

    async for session in get_session():
        segments = await get_segments(session)

    await _render_segments(callback, state, segments, selected, lang, current, max_seg)
    await callback.answer()


@router.callback_query(CatStates.choosing_segments, F.data == "cat:segs_done")
async def on_segments_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[int] = data.get("selected_segments", [])
    lang = data.get("lang", "ru")

    if not selected:
        await callback.answer("Выбери хотя бы одно направление", show_alert=True)
        return

    await state.update_data(selected_segments=selected)

    # Step 2: choose country
    async for session in get_session():
        countries = await get_countries(session)

    text = "В какой стране ищешь клиентов?"
    kb_rows = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        kb_rows.append([InlineKeyboardButton(
            text=f"{flag} {name}", callback_data=f"cat:country:{c.id}",
        )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:search",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_country)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ═══════════════ STEP 2: Choose country ═══════════════

@router.callback_query(CatStates.choosing_country, F.data.startswith("cat:country:"))
async def on_country_chosen(callback: CallbackQuery, state: FSMContext):
    country_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.update_data(country_id=country_id)

    text = "Где именно ищешь?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 По всей стране", callback_data="cat:geo:all")],
        [InlineKeyboardButton(text="🏙 В городах", callback_data="cat:geo:cities")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:to_segments")],
    ])

    await state.set_state(CatStates.choosing_geo)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_country, F.data == "cat:back:to_segments")
async def on_back_to_segments(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CatStates.choosing_segments)
    await on_search_start(callback, state)


# ═══════════════ STEP 3: Choose geo ═══════════════

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:cities")
async def on_geo_cities(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    country_id = data["country_id"]

    async for session in get_session():
        cities = await get_cities(session, country_id)

    selected_cities: list[int] = data.get("selected_cities", [])

    text = f"Выбери города (выбрано: {len(selected_cities)}):"
    kb_rows = []
    for city in cities:
        name = city.name_ru if lang == "ru" else (city.name_en or city.name_ru)
        prefix = "☑️ " if city.id in selected_cities else "⬜ "
        kb_rows.append([InlineKeyboardButton(
            text=f"{prefix}{name}",
            callback_data=f"cat:city:{city.id}",
        )])

    footer = []
    if selected_cities:
        footer.append(InlineKeyboardButton(
            text=f"✅ Готово ({len(selected_cities)})",
            callback_data="cat:cities_done",
        ))
    footer.append(InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_country",
    ))
    kb_rows.append(footer)
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_cities)
    await state.update_data(selected_cities=selected_cities)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


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


@router.callback_query(CatStates.choosing_cities, F.data == "cat:back:to_country")
async def on_back_to_country_from_cities(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    async for session in get_session():
        countries = await get_countries(session)

    text = "В какой стране ищешь клиентов?"
    kb_rows = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        kb_rows.append([InlineKeyboardButton(
            text=f"{flag} {name}", callback_data=f"cat:country:{c.id}",
        )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_segments",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_country)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_cities, F.data == "cat:cities_done")
async def on_cities_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[int] = data.get("selected_cities", [])
    if not selected:
        await callback.answer("Выбери хотя бы один город", show_alert=True)
        return
    await state.update_data(mode="cities")
    await _show_confirmation(callback, state)


# ═══════════════ STEP 4: All country ═══════════════

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:all")
async def on_geo_all(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode="all", selected_cities=[])
    await _show_confirmation(callback, state)


# ═══════════════ CONFIRM & SUBSCRIBE ═══════════════

async def _show_confirmation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    selected_segments: list[int] = data.get("selected_segments", [])
    country_id = data.get("country_id")
    mode = data.get("mode", "all")
    selected_cities: list[int] = data.get("selected_cities", [])

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        existing = await get_user_subscriptions(session, user.id)

    if current + len(selected_segments) > max_seg:
        await callback.answer(f"Лимит: {max_seg}", show_alert=True)
        return

    # Check duplicates
    existing_pairs = {(s.segment_id, s.country_id) for s in existing}
    duplicates = [
        sid for sid in selected_segments
        if (sid, country_id) in existing_pairs
    ]
    if duplicates:
        await callback.answer(f"Уже подписан на {len(duplicates)} из выбранных", show_alert=True)
        return

    text = f"Подтверди подписку:\n\n"
    text += f"📌 Направлений: {len(selected_segments)}\n"
    text += f"🌍 Страна: {country_id}\n"
    if mode == "cities":
        text += f"🏙 Городов: {len(selected_cities)}\n"

    text += "\nНажми «Подписаться» для активации."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="cat:subscribe")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:to_segments")],
    ])

    await state.set_state(CatStates.confirm_subscription)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.confirm_subscription, F.data == "cat:subscribe")
async def on_subscribe(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    selected_segments: list[int] = data.get("selected_segments", [])
    country_id = data["country_id"]
    mode = data.get("mode", "all")
    selected_cities: list[int] = data.get("selected_cities", [])

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return

        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        if current + len(selected_segments) > max_seg:
            await callback.answer(f"Лимит: {max_seg}", show_alert=True)
            return

        # Create subscriptions for all selected segments
        for seg_id in selected_segments:
            await create_subscription(
                session, user_id=user.id,
                segment_id=seg_id, country_id=country_id,
                mode=mode, city_ids=selected_cities if mode == "cities" else None,
            )

        # Activate trial if first subscription
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
            "🎉 Готово! Ты получил 5 дней Business-тарифа.\n"
            f"Подписок создано: {len(selected_segments)}\n\n"
            "Заявки начнут приходить в ближайшее время."
        )
    else:
        text = f"✅ Добавлено подписок: {len(selected_segments)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ═══════════════ SUBSCRIPTIONS LIST ═══════════════

@router.callback_query(F.data == "menu:subs")
async def on_show_subscriptions(callback: CallbackQuery):
    lang = await _get_lang_nostate(callback)

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
        kb_rows.append([InlineKeyboardButton(
            text=f"🗑️ Сегмент #{sub.segment_id} / Страна #{sub.country_id}",
            callback_data=f"sub:del:{sub.id}",
        )])

    if current < max_seg:
        kb_rows.append([InlineKeyboardButton(
            text="➕ Подписаться на направление", callback_data="menu:search",
        )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("sub:del:"))
async def on_delete_subscription(callback: CallbackQuery):
    sub_id = int(callback.data.split(":")[2])
    lang = await _get_lang_nostate(callback)

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        await delete_subscription(session, sub_id, user.id)
        await session.commit()

    await callback.answer("Отписано")
    await on_show_subscriptions(callback)


# ═══════════════ BACK NAVIGATION ═══════════════

@router.callback_query(CatStates.choosing_country, F.data == "menu:search")
async def on_back_to_segments_from_country(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CatStates.choosing_segments)
    await on_search_start(callback, state)


@router.callback_query(CatStates.confirm_subscription, F.data == "cat:back:to_segments")
async def on_back_from_confirm(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CatStates.choosing_segments)
    await on_search_start(callback, state)

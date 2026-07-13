"""FSM catalog navigation: categories → subcategories → country → geo → cities → confirm."""

import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db.crud import (
    cities_within_limit,
    count_user_subscriptions,
    countries_within_limit,
    create_subscription,
    get_categories,
    get_countries,
    get_cities,
    get_max_segments,
    get_segments_by_category,
    get_user,
    get_user_subscriptions,
    delete_subscription,
)
from app.db.session import get_session
from app.locales import get_text

router = Router()


class CatStates(StatesGroup):
    choosing_category = State()
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
    flags = {
        "vn": "🇻🇳", "id": "🇮🇩", "th": "🇹🇭", "ru": "🇷🇺", "tr": "🇹🇷",
        "ae": "🇦🇪", "ge": "🇬🇪", "kz": "🇰🇿", "de": "🇩🇪", "es": "🇪🇸",
        "fr": "🇫🇷", "us": "🇺🇸", "gb": "🇬🇧", "in": "🇮🇳", "cn": "🇨🇳",
        "jp": "🇯🇵", "br": "🇧🇷", "eg": "🇪🇬", "za": "🇿🇦", "it": "🇮🇹",
        "pt": "🇵🇹", "nl": "🇳🇱", "gr": "🇬🇷", "cy": "🇨🇾", "bg": "🇧🇬",
        "ro": "🇷🇴", "hr": "🇭🇷", "cz": "🇨🇿", "pl": "🇵🇱", "hu": "🇭🇺",
        "ie": "🇮🇪", "se": "🇸🇪", "no": "🇳🇴", "fi": "🇫🇮", "dk": "🇩🇰",
        "ca": "🇨🇦", "mx": "🇲🇽", "ar": "🇦🇷", "co": "🇨🇴", "ma": "🇲🇦",
        "tn": "🇹🇳", "kr": "🇰🇷", "ph": "🇵🇭", "my": "🇲🇾", "sg": "🇸🇬",
        "au": "🇦🇺", "nz": "🇳🇿", "il": "🇮🇱", "lb": "🇱🇧", "ke": "🇰🇪",
        "lk": "🇱🇰", "np": "🇳🇵", "mv": "🇲🇻", "kh": "🇰🇭", "la": "🇱🇦",
        "mm": "🇲🇲", "mn": "🇲🇳", "pk": "🇵🇰", "bd": "🇧🇩", "cl": "🇨🇱",
        "pe": "🇵🇪", "ec": "🇪🇨", "cr": "🇨🇷", "pa": "🇵🇦", "do": "🇩🇴",
        "cu": "🇨🇺", "qa": "🇶🇦", "kw": "🇰🇼", "bh": "🇧🇭", "om": "🇴🇲",
        "sa": "🇸🇦", "jo": "🇯🇴", "ch": "🇨🇭", "at": "🇦🇹", "be": "🇧🇪",
        "lt": "🇱🇹", "lv": "🇱🇻", "ee": "🇪🇪", "sk": "🇸🇰", "si": "🇸🇮",
        "al": "🇦🇱", "mk": "🇲🇰", "ba": "🇧🇦", "md": "🇲🇩", "ua": "🇺🇦",
        "az": "🇦🇿", "am": "🇦🇲", "by": "🇧🇾", "rs": "🇷🇸", "me": "🇲🇪",
        "kg": "🇰🇬", "uz": "🇺🇿",
    }
    return flags.get(slug, "🌍")


# ═══════════════ STEP 0: Choose categories ═══════════════

def _count_selected(data: dict) -> int:
    """Count total selected subcategories across all categories."""
    by_cat = data.get("selected_by_cat", {})
    return sum(len(ids) for ids in by_cat.values())


@router.callback_query(F.data == "menu:search")
@router.callback_query(CatStates.choosing_segments, F.data == "cat:back:to_categories")
async def on_show_categories(callback: CallbackQuery, state: FSMContext):
    """Show category picker with selection counter."""
    lang = await _get_lang_nostate(callback)
    data = await state.get_data()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer("Error", show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        categories = await get_categories(session)

    selected_by_cat: dict[str, list[int]] = data.get("selected_by_cat", {})
    total_selected = _count_selected({"selected_by_cat": selected_by_cat})

    await state.update_data(
        lang=lang, plan=user.plan, max_seg=max_seg,
        current_subs=current, selected_by_cat=selected_by_cat,
    )

    text = f"Выбери направления ({current + total_selected}/{max_seg}):\n\n"
    text += "Нажми на категорию чтобы выбрать услуги."

    kb_rows = []
    row = []
    for cat in categories:
        name = cat.title_ru if lang == "ru" else (cat.title_en or cat.title_ru)
        emoji = cat.emoji or ""
        cat_slug = cat.slug
        cat_count = len(selected_by_cat.get(cat_slug, []))
        label = f"{emoji} {name}"
        if cat_count:
            label += f" ({cat_count})"
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"cat:open:{cat.id}:{cat_slug}"
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    if total_selected > 0:
        kb_rows.append([InlineKeyboardButton(
            text=f"✅ Готово ({total_selected} выбрано)",
            callback_data="cat:to_country",
        )])

    kb_rows.append([InlineKeyboardButton(
        text="💬 Нет вашего вида деятельности? Связаться с поддержкой" if lang == "ru" else "💬 Don't see your category? Contact support",
        callback_data="support:missing_category",
    )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_category)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ═══════════════ STEP 1: Choose subcategories within a category ═══════════════

@router.callback_query(CatStates.choosing_category, F.data.startswith("cat:open:"))
async def on_category_open(callback: CallbackQuery, state: FSMContext):
    """Open a category — show its subcategories for multi-select."""
    parts = callback.data.split(":")
    cat_id = int(parts[2])
    cat_slug = parts[3]

    data = await state.get_data()
    lang = data.get("lang", "ru")
    selected_by_cat: dict[str, list[int]] = data.get("selected_by_cat", {})
    selected = selected_by_cat.get(cat_slug, [])

    async for session in get_session():
        segments = await get_segments_by_category(session, cat_id)
        # Load category name in the same session
        cat_name = ""
        if segments:
            from app.db.models import Category
            from sqlalchemy import select
            cat = (await session.execute(select(Category).where(Category.id == cat_id))).scalar_one_or_none()
            cat_name = cat.title_ru if cat else ""
            if cat_name is None:
                cat_name = ""

    # Store both slug and ID in FSM state to avoid DB queries on toggle
    await state.update_data(
        current_category=cat_slug,
        current_category_id=cat_id,
        selected_by_cat=selected_by_cat,
    )

    total_selected = _count_selected({"selected_by_cat": selected_by_cat})
    max_seg = data.get("max_seg", 9)
    current = data.get("current_subs", 0)

    text = f"{cat_name} — выбери услуги ({current + total_selected}/{max_seg}):"

    kb_rows = []
    row = []
    for seg in segments:
        emoji = seg.emoji or ""
        title = seg.title_ru if lang == "ru" else (seg.title_en or seg.title_ru)
        prefix = "✅ " if seg.id in selected else "⬜ "
        row.append(InlineKeyboardButton(
            text=f"{prefix}{emoji} {title}",
            callback_data=f"cat:seg:{seg.id}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    # Back + Subscribe buttons
    footer = []
    footer.append(InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories",
    ))
    if selected:
        footer.append(InlineKeyboardButton(
            text=f"✅ Подписаться ({total_selected})",
            callback_data="cat:to_country",
        ))
    kb_rows.append(footer)

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_segments)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_segments, F.data.startswith("cat:seg:"))
async def on_toggle_segment(callback: CallbackQuery, state: FSMContext):
    """Toggle a subcategory selection — instant, no DB queries."""
    seg_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    cat_slug = data.get("current_category", "")
    cat_id = data.get("current_category_id", 0)
    selected_by_cat: dict[str, list[int]] = data.get("selected_by_cat", {})
    selected = selected_by_cat.get(cat_slug, [])
    total_selected = _count_selected({"selected_by_cat": selected_by_cat})
    max_seg = data.get("max_seg", 9)
    current = data.get("current_subs", 0)

    if seg_id in selected:
        selected.remove(seg_id)
    else:
        if current + total_selected >= max_seg:
            await callback.answer(f"Лимит: {max_seg} направлений", show_alert=True)
            return
        selected.append(seg_id)

    if selected:
        selected_by_cat[cat_slug] = selected
    elif cat_slug in selected_by_cat:
        del selected_by_cat[cat_slug]

    await state.update_data(selected_by_cat=selected_by_cat)

    # Re-render instantly using stored cat_id — no DB roundtrip
    lang = data.get("lang", "ru")
    async for session in get_session():
        segments = await get_segments_by_category(session, cat_id)
        cat_name = ""
        if segments:
            from app.db.models import Category
            from sqlalchemy import select
            cat = (await session.execute(select(Category).where(Category.id == cat_id))).scalar_one_or_none()
            cat_name = cat.title_ru if cat else ""
            if cat_name is None:
                cat_name = ""

    total_after = _count_selected({"selected_by_cat": selected_by_cat})
    text = f"{cat_name} — выбери услуги ({current + total_after}/{max_seg}):"

    kb_rows = []
    row = []
    for seg in segments:
        emoji = seg.emoji or ""
        title = seg.title_ru if lang == "ru" else (seg.title_en or seg.title_ru)
        prefix = "✅ " if seg.id in selected else "⬜ "
        row.append(InlineKeyboardButton(
            text=f"{prefix}{emoji} {title}",
            callback_data=f"cat:seg:{seg.id}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    # Back + Subscribe
    footer = []
    footer.append(InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories",
    ))
    if total_after > 0:
        footer.append(InlineKeyboardButton(
            text=f"✅ Подписаться ({total_after})",
            callback_data="cat:to_country",
        ))
    kb_rows.append(footer)

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_category, F.data == "cat:to_country")
async def on_segments_done(callback: CallbackQuery, state: FSMContext):
    """User clicked 'Done' on category screen — flatten selected subcategories and proceed."""
    data = await state.get_data()
    selected_by_cat: dict[str, list[int]] = data.get("selected_by_cat", {})
    lang = data.get("lang", "ru")

    # Flatten all selected subcategory IDs
    all_selected = []
    for ids in selected_by_cat.values():
        all_selected.extend(ids)

    if not all_selected:
        await callback.answer("Выбери хотя бы одно направление", show_alert=True)
        return

    await state.update_data(selected_segments=all_selected)

    # Proceed to country selection
    await _show_countries(callback, state, lang)


async def _show_countries(callback: CallbackQuery, state: FSMContext, lang: str):
    """Show country picker."""
    async for session in get_session():
        countries = await get_countries(session)

    text = "В какой стране ищешь клиентов?"
    kb_rows = []
    row = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        row.append(InlineKeyboardButton(
            text=f"{flag} {name}", callback_data=f"cat:country:{c.id}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await state.set_state(CatStates.choosing_country)
    await callback.message.edit_text(text, reply_markup=kb)


# ═══════════════ STEP 2: Choose country ═══════════════

def _geo_limit_msg(kind: str, lang: str) -> str:
    """Интерим-сообщение о гео-лимите тарифа (#81).
    TODO T4.1: заменить контекстным пейволлом с кнопкой апгрейда."""
    if kind == "city":
        return ("На этом тарифе — до 3 городов. Профи снимает лимит городов."
                if lang == "ru" else
                "This plan allows up to 3 cities. Pro removes the city limit.")
    return ("На этом тарифе — 1 страна. Профи — до 5 стран."
            if lang == "ru" else
            "This plan allows 1 country. Pro — up to 5 countries.")


@router.callback_query(CatStates.choosing_country, F.data.startswith("cat:country:"))
async def on_country_chosen(callback: CallbackQuery, state: FSMContext):
    country_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    lang = data.get("lang", "ru")

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        existing_countries = (
            {s.country_id for s in await get_user_subscriptions(session, user.id)}
            if user else set()
        )
    plan = user.plan if user else "free"

    # Гео-лимит по стране (#81). При числах v2 обычно подчинён лимиту сегментов.
    if not countries_within_limit(plan, existing_countries, country_id):
        await callback.answer(_geo_limit_msg("country", lang), show_alert=True)
        return

    await state.update_data(country_id=country_id, plan=plan)

    text = "Где именно ищешь?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌍 По всей стране", callback_data="cat:geo:all")],
        [InlineKeyboardButton(text="🏙 В городах", callback_data="cat:geo:cities")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories")],
    ])

    await state.set_state(CatStates.choosing_geo)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_country, F.data == "cat:back:to_categories")
async def on_back_to_categories(callback: CallbackQuery, state: FSMContext):
    await on_show_categories(callback, state)


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
    row = []
    for city in cities:
        name = city.name_ru if lang == "ru" else (city.name_en or city.name_ru)
        prefix = "☑️ " if city.id in selected_cities else "⬜ "
        row.append(InlineKeyboardButton(
            text=f"{prefix}{name}",
            callback_data=f"cat:city:{city.id}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

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
    plan = data.get("plan", "free")
    lang = data.get("lang", "ru")

    if city_id in selected:
        selected.remove(city_id)
    else:
        # Гео-лимит по городам в одной подписке (#81).
        if not cities_within_limit(plan, len(selected) + 1):
            await callback.answer(_geo_limit_msg("city", lang), show_alert=True)
            return
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
    row = []
    for c in countries:
        name = c.name_ru if lang == "ru" else (c.name_en or c.name_ru)
        flag = _country_flag(c.slug)
        row.append(InlineKeyboardButton(
            text=f"{flag} {name}", callback_data=f"cat:country:{c.id}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories",
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

    # Filter out existing subscriptions silently
    existing_pairs = {(s.segment_id, s.country_id) for s in existing}
    new_segments = [
        sid for sid in selected_segments
        if (sid, country_id) not in existing_pairs
    ]
    skipped = len(selected_segments) - len(new_segments)

    if not new_segments:
        await state.clear()
        await on_show_subscriptions(callback)

    await state.update_data(selected_segments=new_segments)

    # Load country name for display
    country_name = f"#{country_id}"
    async for session2 in get_session():
        from app.db.models import Country as CountryModel
        from sqlalchemy import select as sa_sel
        c_res = (await session2.execute(sa_sel(CountryModel).where(CountryModel.id == country_id))).scalar_one_or_none()
        if c_res:
            country_name = c_res.name_ru if lang == "ru" else (c_res.name_en or c_res.name_ru)
        break

    text = f"Подтверди подписку:\n\n"
    text += f"📌 Новых направлений: {len(new_segments)}\n"
    if skipped:
        text += f"📎 Уже подписано: {skipped} (пропущено)\n"
    text += f"🌍 Страна: {country_name}\n"
    if mode == "cities":
        # Load city names
        city_labels = []
        async for session3 in get_session():
            from app.db.models import City as CityModel
            from sqlalchemy import select as sa_sel2
            for cid in selected_cities:
                c_res = (await session3.execute(sa_sel2(CityModel).where(CityModel.id == cid))).scalar_one_or_none()
                if c_res:
                    city_labels.append(c_res.name_ru if lang == "ru" else (c_res.name_en or c_res.name_ru))
            break
        text += f"🏙 Города: {', '.join(city_labels[:5])}\n"

    text += "\nНажми «Подписаться» для активации."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="cat:subscribe")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:to_categories")],
    ])

    await state.set_state(CatStates.confirm_subscription)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.confirm_subscription, F.data == "cat:subscribe")
async def on_subscribe(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    selected_segments: list[int] = data.get("selected_segments", [])
    country_id = data.get("country_id")
    mode = data.get("mode", "all")
    selected_cities: list[int] = data.get("selected_cities", [])

    if not country_id:
        await callback.answer("Ошибка: страна не выбрана. Начни заново.", show_alert=True)
        await state.clear()
        return

    if not selected_segments:
        await callback.answer("Ошибка: направления не выбраны.", show_alert=True)
        await state.clear()
        return

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

        existing_subs = await get_user_subscriptions(session, user.id)

        # Гео-лимиты (control-проверка от гонок/устаревшего стейта) — #81
        existing_countries = {s.country_id for s in existing_subs}
        if not countries_within_limit(user.plan, existing_countries, country_id):
            await callback.answer(_geo_limit_msg("country", lang), show_alert=True)
            return
        if mode == "cities" and not cities_within_limit(user.plan, len(selected_cities)):
            await callback.answer(_geo_limit_msg("city", lang), show_alert=True)
            return

        # Create subscriptions — silently skip duplicates
        created = 0
        existing_pairs = {(s.segment_id, s.country_id) for s in existing_subs}
        for seg_id in selected_segments:
            if (seg_id, country_id) in existing_pairs:
                continue
            await create_subscription(
                session, user_id=user.id,
                segment_id=seg_id, country_id=country_id,
                mode=mode, city_ids=selected_cities if mode == "cities" else None,
            )
            created += 1

        # Activate trial if first subscription
        is_first = current == 0 and created > 0
        if is_first and user.plan == "free":
            from app.config import settings
            user.plan = "trial"
            user.plan_activated_at = datetime.datetime.now(datetime.timezone.utc)
            user.plan_expires_at = user.plan_activated_at + datetime.timedelta(days=settings.trial_days)
            # Notify admin
            from app.userbot.discovery import notify_new_trial
            asyncio.create_task(notify_new_trial(callback.from_user.username, callback.from_user.id, user.source))
            show_upgrade = False
        else:
            show_upgrade = (user.plan == "free")

        await session.commit()

    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()

    await state.clear()

    # Load names for the confirmation message
    seg_names = []
    country_name = ""
    city_labels = []
    async for s2 in get_session():
        from app.db.models import Segment as SegModel, Country as CoModel, City as CiModel
        from sqlalchemy import select as sa_sel2
        for sid in selected_segments:
            seg = (await s2.execute(sa_sel2(SegModel).where(SegModel.id == sid))).scalar_one_or_none()
            if seg:
                name = seg.title_ru if lang == "ru" else (seg.title_en or seg.title_ru)
                seg_names.append(f"{seg.emoji or ''} {name}")
        co = (await s2.execute(sa_sel2(CoModel).where(CoModel.id == country_id))).scalar_one_or_none()
        if co:
            country_name = co.name_ru if lang == "ru" else (co.name_en or co.name_ru)
        if mode == "cities" and selected_cities:
            for cid in selected_cities[:5]:
                ci = (await s2.execute(sa_sel2(CiModel).where(CiModel.id == cid))).scalar_one_or_none()
                if ci:
                    city_labels.append(ci.name_ru if lang == "ru" else (ci.name_en or ci.name_ru))
        break

    if is_first:
        from app.config import settings as _s
        from app.bot.handlers.plan import PLANS as _PLANS
        text = (
            f"🎉 Готово! Тебе открыт пробный период — {_s.trial_days} дней уровня Бизнес.\n\n"
            f"📌 Направления:\n" + "\n".join(seg_names) + "\n"
            f"🌍 Страна: {country_name}\n"
        )
        if city_labels:
            text += f"🏙 Города: {', '.join(city_labels)}\n"
        text += f"\n✅ Создано подписок: {created}\n"
        text += "Заявки с полными контактами начнут приходить в ближайшее время.\n\n"
        text += (
            f"⏳ После пробного периода контакты скроются. "
            f"Тариф Старт открывает их снова — от ${_PLANS['start']['usd_monthly']}/мес."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ])
    else:
        from app.bot.handlers.plan import PLANS as _PLANS
        text = f"✅ Добавлено подписок: {created}\n\n"
        text += "📌\n" + "\n".join(seg_names) + "\n"
        text += f"🌍 {country_name}"
        if city_labels:
            text += f" 🏙 {', '.join(city_labels)}"
        kb_rows = [[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")]]
        if show_upgrade:
            text += (
                "\n\n🔒 На бесплатном тарифе контакты клиентов скрыты.\n"
                "Тариф Старт открывает отправителя и кнопку «Ответить» — отвечай первым."
            )
            kb_rows.insert(0, [InlineKeyboardButton(
                text=f"🎯 Открыть контакты — от ${_PLANS['start']['usd_monthly']}/мес",
                callback_data="menu:plan")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
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

        # Load names for segments and countries
        from app.db.models import Segment, Country, SubscriptionCity, City
        from sqlalchemy import select as sa_select
        segs = (await session.execute(sa_select(Segment))).scalars().all()
        seg_names = {s.id: (s.emoji or "") + " " + (s.title_ru if lang == "ru" else (s.title_en or s.title_ru)) for s in segs}
        countries = (await session.execute(sa_select(Country))).scalars().all()
        country_names = {c.id: c.name_ru if lang == "ru" else (c.name_en or c.name_ru) for c in countries}
        cities_all = (await session.execute(sa_select(City))).scalars().all()
        city_names = {c.id: c.name_ru if lang == "ru" else (c.name_en or c.name_ru) for c in cities_all}
        # Load subscription cities
        sub_cities_map: dict[int, list[str]] = {}
        for sub in subs:
            if sub.mode == "cities":
                sc = (await session.execute(
                    sa_select(SubscriptionCity.city_id).where(SubscriptionCity.subscription_id == sub.id)
                )).scalars().all()
                sub_cities_map[sub.id] = [city_names.get(cid, f"#{cid}") for cid in sc]

    text = f"📋 Мои подписки ({current}/{max_seg})\n\n"
    if not subs:
        text += "У тебя пока нет подписок.\nНажми 🔍 Поиск клиентов чтобы найти первых!"

    kb_rows = []
    for sub in subs:
        seg_name = seg_names.get(sub.segment_id, f"Сегмент #{sub.segment_id}")
        country_name = country_names.get(sub.country_id, f"Страна #{sub.country_id}")
        label = f"🗑️ {seg_name} | {country_name}"
        if sub.mode == "cities" and sub.id in sub_cities_map:
            cities_list = ", ".join(sub_cities_map[sub.id][:3])
            if len(sub_cities_map[sub.id]) > 3:
                cities_list += f" +{len(sub_cities_map[sub.id]) - 3}"
            label += f" | {cities_list}"
        kb_rows.append([InlineKeyboardButton(text=label[:60], callback_data=f"sub:del:{sub.id}")])

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

    from app.cache.subscription_cache import invalidate_all_subscription_caches
    await invalidate_all_subscription_caches()

    await callback.answer("Отписано")
    await on_show_subscriptions(callback)


# ═══════════════ BACK NAVIGATION ═══════════════

@router.callback_query(F.data == "support:missing_category")
async def on_support_missing_category(callback: CallbackQuery):
    """User requests a category not in the list — starts support chat."""
    lang = await _get_lang_nostate(callback)
    from app.db.models import SupportMessage
    from app.db.crud import get_user

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if user:
            msg = SupportMessage(
                user_id=user.id,
                direction="incoming",
                text=f"[Запрос категории] Пользователь @{user.username or user.telegram_id} запрашивает новый вид деятельности.",
            )
            session.add(msg)
            await session.commit()

    text = (
        "📩 Напишите, какой вид деятельности вас интересует, "
        "и мы добавим его в ближайшее время!\n\n"
        "Просто отправьте сообщение в этот чат."
        if lang == "ru"
        else
        "📩 Tell us what category you're looking for, "
        "and we'll add it soon!\n\n"
        "Just send a message in this chat."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ═══════════════ BACK NAVIGATION ═══════════════

@router.callback_query(CatStates.choosing_country, F.data == "menu:search")
async def on_back_to_categories_from_country(callback: CallbackQuery, state: FSMContext):
    await on_show_categories(callback, state)


@router.callback_query(CatStates.confirm_subscription, F.data == "cat:back:to_categories")
async def on_back_from_confirm(callback: CallbackQuery, state: FSMContext):
    await on_show_categories(callback, state)

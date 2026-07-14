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
    plan_has_unlimited_cities,
    get_segments_by_category,
    get_user,
    get_user_subscriptions,
    get_user_city_ids,
    delete_subscription,
)
from app.db.session import get_session
from app.locales import get_text
from app.bot.handlers.plan import paywall_text

router = Router()


class CatStates(StatesGroup):
    choosing_category = State()
    choosing_segments = State()
    choosing_country = State()
    choosing_geo = State()
    choosing_cities = State()
    confirm_subscription = State()


async def _edit_text_or_replace_media(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup
) -> None:
    """Edit a text message, or replace a media welcome with a new text message."""
    if message.text is not None:
        await message.edit_text(text, reply_markup=reply_markup)
        return
    await message.delete()
    await message.answer(text, reply_markup=reply_markup)


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

def trial_days_for_source(source: str) -> int:
    from app.config import settings
    return settings.trial_days + (settings.referral_trial_bonus if source == "referral" else 0)


@router.callback_query(F.data == "menu:search")
@router.callback_query(CatStates.choosing_segments, F.data == "cat:back:to_categories")
async def on_show_categories(callback: CallbackQuery, state: FSMContext):
    """Show category picker with selection counter."""
    lang = await _get_lang_nostate(callback)
    data = await state.get_data()

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
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

    text = get_text(lang, "catalog_categories", current=current + total_selected, limit=max_seg)

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
            text=get_text(lang, "catalog_done", count=total_selected),
            callback_data="cat:to_country",
        )])

    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "catalog_missing"),
        callback_data="support:missing_category",
    )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    from app.analytics import record_event
    await record_event("onboarding_started", user, context={"service_count": current})
    await state.set_state(CatStates.choosing_category)
    await _edit_text_or_replace_media(callback.message, text, kb)
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

    text = get_text(lang, "catalog_services", category=cat_name, current=current + total_selected, limit=max_seg)

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
            text=get_text(lang, "catalog_continue", count=total_selected),
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
            await callback.answer(
                paywall_text("direction", data.get("plan", "free"), data.get("lang", "ru")),
                show_alert=True)
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
    text = get_text(lang, "catalog_services", category=cat_name, current=current + total_after, limit=max_seg)

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
            text=get_text(lang, "catalog_continue", count=total_after),
            callback_data="cat:to_country",
        ))
    kb_rows.append(footer)

    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(CatStates.choosing_category, F.data == "cat:to_country")
@router.callback_query(CatStates.choosing_segments, F.data == "cat:to_country")
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
        await callback.answer(get_text(lang, "catalog_select_service"), show_alert=True)
        return

    await state.update_data(selected_segments=all_selected)

    # Proceed to country selection
    await _show_countries(callback, state, lang)


async def _show_countries(callback: CallbackQuery, state: FSMContext, lang: str):
    """Show country picker."""
    async for session in get_session():
        countries = await get_countries(session)

    text = get_text(lang, "catalog_country")
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

# ═══════════════ STEP 2: Choose country ═══════════════

def _geo_limit_msg(kind: str, plan: str, lang: str) -> str:
    """Гео-лимит тарифа в alert'е воронки (T4.1) — унифицированная копия пейволла.
    Полноэкранный пейволл здесь не подходит: показ экрана потерял бы FSM-выбор."""
    return paywall_text(kind, plan, lang)


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
        await callback.answer(_geo_limit_msg("country", plan, lang), show_alert=True)
        return

    await state.update_data(country_id=country_id, plan=plan)

    await _show_geo_options(callback, state)


@router.callback_query(CatStates.choosing_country, F.data == "cat:back:to_categories")
async def on_back_to_categories(callback: CallbackQuery, state: FSMContext):
    await on_show_categories(callback, state)


async def _show_geo_options(callback: CallbackQuery, state: FSMContext) -> None:
    """Show geo mode and make Back return to the country picker."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    plan = data.get("plan", "free")
    rows = []
    if plan_has_unlimited_cities(plan):
        rows.append([InlineKeyboardButton(
            text=get_text(lang, "catalog_all_country"), callback_data="cat:geo:all",
        )])
    rows.append([InlineKeyboardButton(
        text=get_text(lang, "catalog_select_cities"), callback_data="cat:geo:cities",
    )])
    rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="cat:back:to_country",
    )])
    await state.set_state(CatStates.choosing_geo)
    await callback.message.edit_text(
        get_text(lang, "catalog_geo"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(CatStates.choosing_geo, F.data == "cat:back:to_country")
async def on_back_to_country_from_geo(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _show_countries(callback, state, data.get("lang", "ru"))


# ═══════════════ STEP 3: Choose geo ═══════════════

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:cities")
async def on_geo_cities(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    country_id = data["country_id"]

    async for session in get_session():
        cities = await get_cities(session, country_id)
        user = await get_user(session, callback.from_user.id)
        existing_city_ids = await get_user_city_ids(session, user.id) if user else set()

    selected_cities: list[int] = data.get("selected_cities", [])

    text = get_text(lang, "catalog_cities", count=len(selected_cities))
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
    await state.update_data(
        selected_cities=selected_cities, existing_city_ids=list(existing_city_ids),
    )
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
        # Лимит считается по distinct-городам во всех поисках пользователя.
        existing_city_ids = set(data.get("existing_city_ids", []))
        total_city_ids = existing_city_ids | set(selected) | {city_id}
        if not cities_within_limit(plan, len(total_city_ids)):
            await callback.answer(_geo_limit_msg("city", plan, lang), show_alert=True)
            return
        selected.append(city_id)

    await state.update_data(selected_cities=selected)
    await on_geo_cities(callback, state)


@router.callback_query(CatStates.choosing_cities, F.data == "cat:back:to_country")
async def on_back_to_geo_from_cities(callback: CallbackQuery, state: FSMContext):
    await _show_geo_options(callback, state)


@router.callback_query(CatStates.choosing_cities, F.data == "cat:cities_done")
async def on_cities_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected: list[int] = data.get("selected_cities", [])
    if not selected:
        await callback.answer(get_text(data.get("lang", "ru"), "catalog_select_city"), show_alert=True)
        return
    await state.update_data(mode="cities")
    await _show_confirmation(callback, state)


# ═══════════════ STEP 4: All country ═══════════════

@router.callback_query(CatStates.choosing_geo, F.data == "cat:geo:all")
async def on_geo_all(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("plan", "free")
    lang = data.get("lang", "ru")
    if not plan_has_unlimited_cities(plan):
        await callback.answer(_geo_limit_msg("city", plan, lang), show_alert=True)
        return
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
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        existing = await get_user_subscriptions(session, user.id)
        user_plan = user.plan

    if current + len(selected_segments) > max_seg:
        await callback.answer(paywall_text("direction", user_plan, lang), show_alert=True)
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
        return

    await state.update_data(selected_segments=new_segments)

    # Load selected service names and country name for display
    segment_labels = []
    country_name = f"#{country_id}"
    async for session2 in get_session():
        from app.db.models import Country as CountryModel, Segment as SegmentModel
        from sqlalchemy import select as sa_sel
        c_res = (await session2.execute(sa_sel(CountryModel).where(CountryModel.id == country_id))).scalar_one_or_none()
        if c_res:
            country_name = c_res.name_ru if lang == "ru" else (c_res.name_en or c_res.name_ru)
        segments = (await session2.execute(
            sa_sel(SegmentModel).where(SegmentModel.id.in_(new_segments))
        )).scalars().all()
        segment_by_id = {segment.id: segment for segment in segments}
        for segment_id in new_segments:
            segment = segment_by_id.get(segment_id)
            if segment:
                name = segment.title_ru if lang == "ru" else (segment.title_en or segment.title_ru)
                segment_labels.append("• {} {}".format(segment.emoji or "", name).strip())
        break

    text = get_text(lang, "catalog_confirm") + "\n\n"
    text += get_text(lang, "catalog_new_services", count=len(new_segments)) + "\n"
    text += get_text(lang, "search_scope_services") + "\n"
    text += "\n".join(segment_labels) + "\n"
    if skipped:
        text += get_text(lang, "catalog_skipped", count=skipped) + "\n"
    text += get_text(lang, "catalog_country_line", country=country_name) + "\n"
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
        text += get_text(lang, "catalog_cities_line", cities=", ".join(city_labels[:5])) + "\n"

    text += "\n" + get_text(lang, "catalog_activate_hint")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "catalog_activate"), callback_data="cat:subscribe")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="cat:back:previous")],
    ])

    from app.analytics import record_event
    await record_event("search_confirmation_viewed", user, context={"service_count": len(new_segments), "country_id": country_id, "city_count": len(selected_cities), "mode": mode})
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
        await callback.answer(get_text(lang, "catalog_error_country"), show_alert=True)
        await state.clear()
        return

    if not selected_segments:
        await callback.answer(get_text(lang, "catalog_error_services"), show_alert=True)
        await state.clear()
        return
    trial_length = 0
    trial_expiry_text = ""

    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return

        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        if current + len(selected_segments) > max_seg:
            await callback.answer(paywall_text("direction", user.plan, lang), show_alert=True)
            return

        existing_subs = await get_user_subscriptions(session, user.id)

        # Гео-лимиты (control-проверка от гонок/устаревшего стейта) — #81
        existing_countries = {s.country_id for s in existing_subs}
        if not countries_within_limit(user.plan, existing_countries, country_id):
            await callback.answer(_geo_limit_msg("country", user.plan, lang), show_alert=True)
            return
        if mode == "cities":
            existing_city_ids = await get_user_city_ids(session, user.id)
            total_city_ids = existing_city_ids | set(selected_cities)
            if not cities_within_limit(user.plan, len(total_city_ids)):
                await callback.answer(_geo_limit_msg("city", user.plan, lang), show_alert=True)
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
            from app.db.crud import set_onboarded
            await set_onboarded(session, callback.from_user.id)
            trial_length = trial_days_for_source(user.source)
            user.plan = "trial"
            user.plan_activated_at = datetime.datetime.now(datetime.timezone.utc)
            user.plan_expires_at = user.plan_activated_at + datetime.timedelta(days=trial_length)
            trial_expiry_text = user.plan_expires_at.strftime("%d.%m.%Y")
            # Notify admin
            from app.userbot.discovery import notify_new_trial
            asyncio.create_task(notify_new_trial(callback.from_user.username, callback.from_user.id, user.source))
            show_upgrade = False
        else:
            show_upgrade = (user.plan == "free")

        await session.commit()
        from app.analytics import record_event
        await record_event("search_created", user, context={"service_count": created, "country_id": country_id, "city_count": len(selected_cities), "mode": mode})
        if is_first:
            await record_event("trial_started", user)

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
        text = get_text(lang, "trial_started", date=trial_expiry_text) + "\n\n" + (
            get_text(lang, "search_scope_services") + "\n" + "\n".join(seg_names) + "\n" +
            get_text(lang, "catalog_country_line", country=country_name) + "\n"
        )
        if city_labels:
            text += get_text(lang, "catalog_cities_line", cities=", ".join(city_labels)) + "\n"
        text += "\n" + get_text(lang, "search_created", count=created) + "\n"
        text += get_text(lang, "search_delivery") + "\n\n"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "btn_main_menu"), callback_data="menu:main")],
        ])
    else:
        from app.bot.handlers.plan import PLANS as _PLANS
        text = get_text(lang, "search_added", count=created) + "\n\n"
        text += get_text(lang, "search_scope_services") + "\n" + "\n".join(seg_names) + "\n"
        text += get_text(lang, "search_scope_country", country=country_name)
        if city_labels:
            text += " " + get_text(lang, "search_scope_cities", cities=", ".join(city_labels))
        kb_rows = [[InlineKeyboardButton(text=get_text(lang, "btn_main_menu"), callback_data="menu:main")]]
        if show_upgrade:
            text += "\n\n" + get_text(lang, "free_after_search")
            kb_rows.insert(0, [InlineKeyboardButton(
                text=get_text(lang, "lead_btn_unlock", price=_PLANS["start"]["usd_monthly"]),
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
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
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

    text = get_text(lang, "searches_title", current=current, limit=max_seg) + "\n\n"
    if not subs:
        text += get_text(lang, "searches_empty")

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
            text=get_text(lang, "btn_add_search"), callback_data="menu:search",
        )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await callback.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("sub:del:"))
async def on_delete_subscription_prompt(callback: CallbackQuery):
    sub_id = int(callback.data.split(":")[2])
    lang = await _get_lang_nostate(callback)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_delete_search"), callback_data=f"sub:confirm_del:{sub_id}")],
        [InlineKeyboardButton(text=get_text(lang, "btn_cancel"), callback_data="menu:subs")],
    ])
    await callback.message.edit_text(get_text(lang, "search_delete_confirm"), reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("sub:confirm_del:"))
async def on_delete_subscription(callback: CallbackQuery):
    sub_id = int(callback.data.split(":")[2])
    lang = await _get_lang_nostate(callback)
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error_generic"), show_alert=True)
            return
        deleted = await delete_subscription(session, sub_id, user.id)
        await session.commit()
    if deleted:
        from app.cache.subscription_cache import invalidate_all_subscription_caches
        await invalidate_all_subscription_caches()
        await callback.answer(get_text(lang, "item_deleted"))
    else:
        await callback.answer(get_text(lang, "item_not_found"), show_alert=True)
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
@router.callback_query(CatStates.confirm_subscription, F.data == "cat:back:previous")
async def on_back_from_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data.get("mode") == "cities":
        await on_geo_cities(callback, state)
        return
    await _show_geo_options(callback, state)


def _selected_segments_from_keyboard(callback: CallbackQuery) -> list[int]:
    """Recover checked segment IDs from a stale pre-Redis subcategory screen."""
    markup = callback.message.reply_markup
    if not markup:
        return []
    selected = []
    for row in markup.inline_keyboard:
        for button in row:
            data = button.callback_data or ""
            if data.startswith("cat:seg:") and button.text.startswith("✅"):
                selected.append(int(data.rsplit(":", 1)[1]))
    return selected


@router.callback_query(F.data == "cat:to_country")
async def recover_stale_continue(callback: CallbackQuery, state: FSMContext):
    """Recover Continue buttons created before persistent FSM was enabled."""
    selected = _selected_segments_from_keyboard(callback)
    if not selected:
        await state.clear()
        await on_show_categories(callback, state)
        return
    lang = await _get_lang_nostate(callback)
    async for session in get_session():
        user = await get_user(session, callback.from_user.id)
        current = await count_user_subscriptions(session, user.id) if user else 0
    plan = user.plan if user else "free"
    await state.update_data(
        lang=lang, plan=plan, current_subs=current, max_seg=get_max_segments(plan),
        selected_by_cat={"recovered": selected},
    )
    await on_segments_done(callback, state)


@router.callback_query(F.data == "cat:back:to_categories")
async def recover_stale_back(callback: CallbackQuery, state: FSMContext):
    """Make stale Back buttons useful after an old in-memory FSM was lost."""
    await state.clear()
    await on_show_categories(callback, state)

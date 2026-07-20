from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

from app.db.crud import get_or_create_user, set_language
from app.db.session import get_session
from app.locales import get_text

router = Router()


# ── /start ──

@router.message(CommandStart())
async def cmd_start(message: Message):
    from aiogram.filters import CommandObject
    import datetime as dt

    # Extract referral code from deep link
    ref_code = None
    if message.text and "ref_" in message.text:
        parts = message.text.split()
        if len(parts) > 1:
            arg = parts[1]
            if arg.startswith("ref_"):
                ref_code = arg[4:]

    async for session in get_session():
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
        )
        lang = user.language

        # Process referral — immutable edge; code lives on users.referral_code.
        if ref_code and user.source == "direct" and user.created_at and \
           (dt.datetime.now(dt.timezone.utc) - user.created_at).total_seconds() < 60:
            from app.db.models import Referral, User
            from sqlalchemy import select
            referrer = (await session.execute(
                select(User).where(User.referral_code == ref_code)
            )).scalar_one_or_none()
            if referrer and referrer.id != user.id:
                already = (await session.execute(
                    select(Referral).where(Referral.referral_id == user.id)
                )).scalar_one_or_none()
                if already is None:
                    user.source = "referral"
                    session.add(Referral(
                        referrer_id=referrer.id,
                        referral_id=user.id,
                        ref_code=ref_code,
                        status="pending",
                    ))
                    # Referral changes acquisition and future trial duration only.
                    # Trial starts after the first search is committed (U3).

        from app.analytics import record_event
        await record_event("welcome_viewed", user)
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

    # Text welcome keeps the whole onboarding flow editable in place.
    await message.answer(text, reply_markup=kb)


# ── Language selection ──

@router.callback_query(F.data.startswith("lang:"))
async def on_language_select(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":")[1]

    async for session in get_session():
        await set_language(session, callback.from_user.id, lang)
        user = await get_or_create_user(session, callback.from_user.id, callback.from_user.username)
        is_onboarded = user.onboarded
        from app.analytics import record_event
        await record_event("language_selected", user, context={"success": True})
        await session.commit()

    if not is_onboarded:
        from app.bot.handlers.catalog_nav import on_show_categories
        await state.clear()
        await on_show_categories(callback, state)
        return
    else:
        await _show_menu_from_db(callback.message, callback.from_user.id)
    await callback.answer()


# ── Main menu ──

async def _show_menu_from_db(message: Message, telegram_id: int):
    """Show main menu using language and plan from DB."""
    import datetime
    plan = "free"
    user_id = None
    async for session in get_session():
        from app.db.crud import get_user
        from app.bot.handlers.plan import plan_display_name
        user = await get_user(session, telegram_id)
        lang = user.language if user else "ru"
        plan_name = "Free"
        if user:
            plan = user.plan
            user_id = user.id
            from app.db.crud import count_user_subscriptions
            search_count = await count_user_subscriptions(session, user.id)
            has_searches = search_count > 0
            plan_name = plan_display_name(user.plan, lang)
            if user.plan in ("trial", "start", "pro", "business") and user.plan_expires_at:
                days_left = (user.plan_expires_at - datetime.datetime.now(datetime.timezone.utc)).days
                plan_name = f"{plan_name} ({get_text(lang, 'plan_until', date=user.plan_expires_at.strftime('%d.%m.%Y'))})"
    has_searches = locals().get("has_searches", False)
    search_count = locals().get("search_count", 0)
    matched = await _matched_today(user_id) if user_id else 0
    await _show_menu(message, lang, plan_name, matched=matched, is_free=(plan == "free"), has_searches=has_searches, search_count=search_count)


async def _matched_today(user_id: int) -> int:
    """Заявок сматчено пользователю сегодня (stats:daily:{id}:{date}:matched, D2)."""
    import datetime
    from app.cache import get_redis
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    redis = await get_redis()
    return int(await redis.get(f"stats:daily:{user_id}:{today}:matched") or 0)


async def _show_menu(message: Message, lang: str, plan_name: str = "Free",
                     matched: int = 0, is_free: bool = True, has_searches: bool = False, search_count: int = 0):
    text = (
        f"{get_text(lang, 'menu_header')}\n\n"
        f"{get_text(lang, 'menu_plan', plan=plan_name)}\n"
        f"{get_text(lang, 'menu_notifications', matched=matched)}\n"
        f"{get_text(lang, 'menu_searches', count=search_count)}\n"
    )
    if is_free:
        text += f"{get_text(lang, 'menu_free_hidden')}\n"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_text(lang, "btn_searches" if has_searches else "btn_search"), callback_data="menu:subs" if has_searches else "menu:search")],
            [InlineKeyboardButton(text=get_text(lang, "btn_results"), callback_data="menu:stats")],
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


# ── Command shortcuts → direct screens (no emoji-only bridge) ──

@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    """Open the category picker directly."""
    from app.bot.handlers.catalog_nav import CatStates
    from app.db.crud import get_user, count_user_subscriptions, get_max_segments, get_categories

    await state.clear()
    lang = await _get_user_lang_for_message(message)

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            await message.answer(get_text(lang, "error_user_not_found"))
            return
        current = await count_user_subscriptions(session, user.id)
        max_seg = get_max_segments(user.plan)
        categories = await get_categories(session)

    await state.update_data(
        lang=lang, plan=user.plan, max_seg=max_seg,
        current_subs=current, selected_by_cat={},
    )

    # Build category picker keyboard
    text = get_text(lang, "catalog_categories", current=current, limit=max_seg)

    kb_rows = []
    row = []
    for cat in categories:
        name = cat.title_ru if lang == "ru" else (cat.title_en or cat.title_ru)
        emoji = cat.emoji or ""
        row.append(InlineKeyboardButton(
            text=f"{emoji} {name}",
            callback_data=f"cat:open:{cat.id}:{cat.slug}",
        ))
        if len(row) == 2:
            kb_rows.append(row)
            row = []
    if row:
        kb_rows.append(row)

    kb_rows.append([InlineKeyboardButton(
        text="💬 Нет вашего вида деятельности? Связаться с поддержкой" if lang == "ru" else "💬 Don't see your category? Contact support",
        callback_data="support:missing_category",
    )])
    kb_rows.append([InlineKeyboardButton(
        text=get_text(lang, "btn_back"), callback_data="menu:main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await message.answer(text, reply_markup=kb)
    await state.set_state(CatStates.choosing_category)

@router.message(Command("keywords"))
async def cmd_keywords(message: Message):
    """Show keywords list directly."""
    from app.bot.handlers.keywords import show_keywords_via_message
    lang = await _get_user_lang_for_message(message)
    await show_keywords_via_message(message, lang)

@router.message(Command("channels"))
async def cmd_channels(message: Message):
    """Show channels list directly."""
    from app.bot.handlers.channels import show_channels_via_message
    lang = await _get_user_lang_for_message(message)
    await show_channels_via_message(message, lang)

@router.message(Command("subscriptions"))
async def cmd_subscriptions(message: Message):
    """Show subscriptions list directly."""
    lang = await _get_user_lang_for_message(message)
    await _show_subscriptions_via_message(message, lang)

@router.message(Command("plan"))
async def cmd_plan(message: Message):
    """Show plan & payment screen directly."""
    lang = await _get_user_lang_for_message(message)
    await _show_plan_via_message(message, lang)

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Show settings screen directly."""
    lang = await _get_user_lang_for_message(message)
    await _show_settings_via_message(message, lang)

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Show lead statistics directly (T5.1)."""
    from app.bot.handlers.discover import build_stats_screen
    from app.db.crud import get_user
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        lang = user.language if user else "ru"
    text, kb = await build_stats_screen(user, lang)
    await message.answer(text, reply_markup=kb)


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    await message.answer(f"Chat ID: `{message.chat.id}`")


# ── Message-based display helpers (used by /command shortcuts) ──

async def _get_user_lang_for_message(message: Message) -> str:
    """Get user language from DB using a Message (not CallbackQuery)."""
    from app.db.crud import get_user
    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        return user.language if user else "ru"


async def _show_subscriptions_via_message(message: Message, lang: str):
    """Show subscriptions list via message.answer() — used by /subscriptions."""
    from app.db.crud import get_user, get_user_subscriptions, get_max_segments, get_max_countries
    from app.db.models import Segment, Country, SubscriptionCity, City
    from sqlalchemy import select as sa_select

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        if not user:
            return
        subs = await get_user_subscriptions(session, user.id)
        current = len(subs)
        max_seg = get_max_segments(user.plan)
        distinct_countries = len({s.country_id for s in subs})
        max_countries = get_max_countries(user.plan)

        segs = (await session.execute(sa_select(Segment))).scalars().all()
        seg_names = {s.id: (s.emoji or "") + " " + (s.title_ru if lang == "ru" else (s.title_en or s.title_ru)) for s in segs}
        countries = (await session.execute(sa_select(Country))).scalars().all()
        country_names = {c.id: c.name_ru if lang == "ru" else (c.name_en or c.name_ru) for c in countries}
        cities_all = (await session.execute(sa_select(City))).scalars().all()
        city_names = {c.id: c.name_ru if lang == "ru" else (c.name_en or c.name_ru) for c in cities_all}
        sub_cities_map: dict[int, list[str]] = {}
        for sub in subs:
            if sub.mode == "cities":
                sc = (await session.execute(
                    sa_select(SubscriptionCity.city_id).where(SubscriptionCity.subscription_id == sub.id)
                )).scalars().all()
                sub_cities_map[sub.id] = [city_names.get(cid, f"#{cid}") for cid in sc]

    countries_cap = "∞" if max_countries >= 9999 else str(max_countries)
    text = get_text(lang, "searches_title", current=current, limit=max_seg) + "\n\n"
    if subs:
        text += get_text(lang, "searches_countries", current=distinct_countries, limit=countries_cap) + "\n\n"
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
    kb_rows.append([InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await message.answer(text, reply_markup=kb)


async def _show_plan_via_message(message: Message, lang: str):
    """Show plan & payment screen via message.answer() — used by /plan.
    Единый рендер с экраном menu:plan (T3.1) — без рассинхрона."""
    from app.db.crud import get_user
    from app.bot.handlers.plan import build_plan_screen

    async for session in get_session():
        user = await get_user(session, message.from_user.id)
        text, kb = build_plan_screen(user, lang)
    await message.answer(text, reply_markup=kb)


async def _show_settings_via_message(message: Message, lang: str):
    """Show settings screen via message.answer() — used by /settings."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text(lang, "btn_keywords"), callback_data="menu:keywords")],
        [InlineKeyboardButton(text=get_text(lang, "btn_channels"), callback_data="menu:channels")],
        [InlineKeyboardButton(text=get_text(lang, "btn_subscriptions"), callback_data="menu:subs")],
        [InlineKeyboardButton(text=get_text(lang, "btn_stats"), callback_data="menu:stats")],
        [InlineKeyboardButton(text=get_text(lang, "btn_csv"), callback_data="menu:csv")],
        [InlineKeyboardButton(text=get_text(lang, "btn_digest"), callback_data="menu:digest")],
        [InlineKeyboardButton(text=get_text(lang, "btn_language"), callback_data="menu:language")],
        [InlineKeyboardButton(
            text="📖 Инструкции" if lang == "ru" else "📖 Instructions",
            callback_data="menu:instructions",
        )],
        [InlineKeyboardButton(text=get_text(lang, "btn_about"), callback_data="menu:about")],
        [InlineKeyboardButton(text=get_text(lang, "btn_back"), callback_data="menu:main")],
    ])
    await message.answer(
        "⚙️ Settings" if lang == "en" else "⚙️ Настройки",
        reply_markup=kb,
    )


# ── Helpers ──

def _detect_lang_from_message(message: Message) -> str:
    """Detect language from message text — simple heuristic."""
    text = message.text or message.caption or ""
    if "Русский" in text or "русский" in text.lower() or "Выбери" in text:
        return "ru"
    return "en"

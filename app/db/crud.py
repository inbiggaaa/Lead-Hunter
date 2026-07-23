from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    User,
    Keyword,
    WatchedChat,
    UserSubscription,
    SubscriptionCity,
    Country,
    City,
    Segment,
    SegmentKeyword,
    SegmentLLMProfile,
)

# ── Users ──

async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None = None) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.flush()
    elif username and user.username != username:
        user.username = username
    return user


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def set_language(session: AsyncSession, telegram_id: int, language: str) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(language=language)
    )


async def set_onboarded(session: AsyncSession, telegram_id: int) -> None:
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(onboarded=True)
    )


# ── Keywords ──

async def get_keywords(session: AsyncSession, user_id: int) -> list[Keyword]:
    result = await session.execute(
        select(Keyword).where(Keyword.user_id == user_id, Keyword.is_active == True).order_by(Keyword.created_at)
    )
    return list(result.scalars().all())


async def count_keywords(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(Keyword.id)).where(Keyword.user_id == user_id, Keyword.is_active == True)
    )
    return result.scalar() or 0


async def add_keyword(session: AsyncSession, user_id: int, text: str, is_regex: bool = False) -> Keyword:
    kw = Keyword(user_id=user_id, text=text, is_regex=is_regex)
    session.add(kw)
    await session.flush()
    return kw


async def delete_keyword(session: AsyncSession, kw_id: int, user_id: int) -> bool:
    result = await session.execute(
        delete(Keyword).where(Keyword.id == kw_id, Keyword.user_id == user_id)
    )
    return result.rowcount > 0


# ── Watched chats ──

async def get_watched_chats(session: AsyncSession, user_id: int) -> list[WatchedChat]:
    result = await session.execute(
        select(WatchedChat).where(WatchedChat.user_id == user_id, WatchedChat.status == "approved")
        .order_by(WatchedChat.created_at)
    )
    return list(result.scalars().all())


async def count_watched_chats(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(WatchedChat.id)).where(
            WatchedChat.user_id == user_id, WatchedChat.status == "approved"
        )
    )
    return result.scalar() or 0


async def add_watched_chat(
    session: AsyncSession,
    user_id: int,
    chat_username: str,
    title: str | None = None,
    is_private: bool = False,
) -> WatchedChat:
    chat = WatchedChat(
        user_id=user_id,
        chat_username=chat_username,
        source="manual",
        title=title,
        is_private=is_private,
        status="pending" if is_private else "approved",
    )
    session.add(chat)
    await session.flush()
    return chat


async def delete_watched_chat(session: AsyncSession, chat_id: int, user_id: int) -> bool:
    result = await session.execute(
        delete(WatchedChat).where(WatchedChat.id == chat_id, WatchedChat.user_id == user_id)
    )
    return result.rowcount > 0


# ── Catalog ──

async def get_countries(session: AsyncSession) -> list[Country]:
    result = await session.execute(
        select(Country).where(Country.is_active == True).order_by(Country.name_ru)
    )
    return list(result.scalars().all())


async def get_cities(session: AsyncSession, country_id: int) -> list[City]:
    result = await session.execute(
        select(City).where(City.country_id == country_id, City.is_active == True).order_by(City.name_ru)
    )
    return list(result.scalars().all())


async def get_segments(session: AsyncSession) -> list[Segment]:
    result = await session.execute(
        select(Segment).where(Segment.is_active == True).order_by(Segment.sort_order)
    )
    return list(result.scalars().all())


async def get_categories(session: AsyncSession) -> list:
    """Return active categories ordered by sort_order."""
    from app.db.models import Category
    result = await session.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order)
    )
    return list(result.scalars().all())


async def get_segments_by_category(session: AsyncSession, category_id: int) -> list[Segment]:
    """Return active subcategories for a given category."""
    result = await session.execute(
        select(Segment)
        .where(Segment.category_id == category_id, Segment.is_active == True)
        .order_by(Segment.sort_order)
    )
    return list(result.scalars().all())


# ── User subscriptions ──

async def count_user_subscriptions(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(
        select(func.count(UserSubscription.id)).where(UserSubscription.user_id == user_id)
    )
    return result.scalar() or 0


async def get_user_subscriptions(session: AsyncSession, user_id: int) -> list[UserSubscription]:
    result = await session.execute(
        select(UserSubscription).where(UserSubscription.user_id == user_id)
    )
    return list(result.scalars().all())


async def create_subscription(
    session: AsyncSession,
    user_id: int,
    segment_id: int,
    country_id: int,
    mode: str = "all",
    city_ids: list[int] | None = None,
) -> UserSubscription:
    sub = UserSubscription(user_id=user_id, segment_id=segment_id, country_id=country_id, mode=mode)
    session.add(sub)
    await session.flush()

    if mode == "cities" and city_ids:
        for city_id in city_ids:
            session.add(SubscriptionCity(subscription_id=sub.id, city_id=city_id))
        await session.flush()

    return sub


async def delete_subscription(session: AsyncSession, sub_id: int, user_id: int) -> bool:
    result = await session.execute(
        delete(UserSubscription).where(UserSubscription.id == sub_id, UserSubscription.user_id == user_id)
    )
    return result.rowcount > 0


# ── Limits helpers (тарифы v2, #81 — единая матрица) ──

# Города не лимитируются ни на одном тарифе; sentinel нужен только для UI.
_GEO_UNLIMITED = 9999


def _plan_limits(plan: str) -> dict:
    """Матрица лимитов покрытия. Неизвестный план → free (least privilege)."""
    from app.config import settings
    pro = {
        "segments": settings.max_segments_pro,
        "channels": settings.max_channels_pro,
        "keywords": settings.max_keywords_pro,
        "countries": settings.max_countries_pro, "cities": _GEO_UNLIMITED,
    }
    business = {
        "segments": settings.max_segments_business,
        "channels": settings.max_channels_business,
        "keywords": settings.max_keywords_business,
        "countries": settings.max_countries_business, "cities": _GEO_UNLIMITED,
    }
    matrix = {
        "free": {
            "segments": settings.max_segments_free, "channels": settings.max_channels_free,
            "keywords": settings.max_keywords_free, "countries": settings.max_countries_start,
            "cities": _GEO_UNLIMITED,
        },
        "start": {
            "segments": settings.max_segments_start, "channels": settings.max_channels_start,
            "keywords": settings.max_keywords_start, "countries": settings.max_countries_start,
            "cities": _GEO_UNLIMITED,
        },
        "pro": pro, "business": business, "trial": pro,
    }
    return matrix.get(plan, matrix["free"])


def get_max_keywords(plan: str) -> int:
    return _plan_limits(plan)["keywords"]


def get_max_channels(plan: str) -> int:
    return _plan_limits(plan)["channels"]


def get_max_segments(plan: str) -> int:
    return _plan_limits(plan)["segments"]


def get_max_countries(plan: str) -> int:
    return _plan_limits(plan)["countries"]


def get_max_cities(plan: str) -> int:
    """Максимум distinct-городов суммарно по всем поискам пользователя."""
    return _plan_limits(plan)["cities"]


def plan_has_unlimited_cities(plan: str) -> bool:
    """Режим всей страны доступен на каждом тарифе."""
    return True


async def count_leads_since(session: AsyncSession, user_id: int, since) -> int:
    """T7.2: число доставленных заявок пользователю с момента `since` (из sent_log)."""
    from app.db.models import SentLog
    return (await session.execute(
        select(func.count(SentLog.id)).where(
            SentLog.user_id == user_id, SentLog.sent_at >= since)
    )).scalar() or 0


async def get_paid_subscriber_ids(session: AsyncSession) -> set:
    """T7.2: user_id всех, у кого есть ОПЛАЧЕННАЯ подписка (отличить бывших платящих от бывших триалов)."""
    from app.db.models import Subscription
    rows = (await session.execute(
        select(Subscription.user_id).where(Subscription.payment_status == "paid").distinct()
    )).scalars().all()
    return set(rows)


async def get_sent_log_for_export(session: AsyncSession, user_id: int, days: int) -> list:
    """T5.2: строки sent_log пользователя за `days` дней для CSV (метаданные, без текста)."""
    from datetime import datetime, timedelta, timezone
    from app.db.models import SentLog
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(SentLog).where(SentLog.user_id == user_id, SentLog.sent_at >= since)
        .order_by(SentLog.sent_at.desc())
    )).scalars().all()
    return list(rows)


async def get_daily_lead_counts(session: AsyncSession, user_id: int, days: int) -> dict:
    """T5.1: {дата 'YYYY-MM-DD' → число доставленных заявок} за последние `days` дней (из sent_log)."""
    from datetime import datetime, timedelta, timezone
    from app.db.models import SentLog
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(func.date(SentLog.sent_at), func.count(SentLog.id))
        .where(SentLog.user_id == user_id, SentLog.sent_at >= since)
        .group_by(func.date(SentLog.sent_at))
    )).all()
    return {str(d): c for d, c in rows}


async def get_user_city_ids(session: AsyncSession, user_id: int) -> set[int]:
    """Distinct города во всех поисках пользователя для общего лимита тарифа."""
    rows = await session.execute(
        select(SubscriptionCity.city_id)
        .join(UserSubscription, UserSubscription.id == SubscriptionCity.subscription_id)
        .where(UserSubscription.user_id == user_id)
    )
    return set(rows.scalars().all())


def cities_within_limit(plan: str, n_cities: int) -> bool:
    """Города не ограничиваются тарифом; лимиты действуют на страны и направления."""
    return True


def countries_within_limit(plan: str, existing_country_ids, new_country_id: int) -> bool:
    """Добавление страны не выводит число distinct-стран за лимит плана.
    При утверждённых числах v2 обычно подчинён лимиту подписок (стран = сегментов),
    но защищает при их будущей смене через .env."""
    return len(set(existing_country_ids) | {new_country_id}) <= get_max_countries(plan)


# ── Segment LLM profiles ──

class SegmentLLMProfileValidationError(ValueError):
    """Invalid segment LLM profile payload (CRUD gate before flush)."""


def _normalize_profile_locale(locale: str) -> str:
    normalized = (locale or "").strip().lower()
    if not normalized or len(normalized) > 10:
        raise SegmentLLMProfileValidationError("locale must be 1–10 chars")
    return normalized


def _validate_profile_string_list(field: str, value: object) -> list[str]:
    if not isinstance(value, list):
        raise SegmentLLMProfileValidationError(f"{field} must be a list of strings")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise SegmentLLMProfileValidationError(f"{field} items must be strings")
        text = item.strip()
        if not text:
            raise SegmentLLMProfileValidationError(f"{field} items must be non-empty")
        cleaned.append(text)
    return cleaned


def _validate_target_lead(target_lead: str) -> str:
    text = (target_lead or "").strip()
    if not text:
        raise SegmentLLMProfileValidationError("target_lead must be non-empty")
    return text


def _validate_profile_version(version: int) -> int:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise SegmentLLMProfileValidationError("version must be a positive integer")
    return version


async def get_segment_llm_profile(
    session: AsyncSession,
    *,
    segment_id: int,
    locale: str = "ru",
) -> SegmentLLMProfile | None:
    locale = _normalize_profile_locale(locale)
    result = await session.execute(
        select(SegmentLLMProfile).where(
            SegmentLLMProfile.segment_id == segment_id,
            SegmentLLMProfile.locale == locale,
        )
    )
    return result.scalar_one_or_none()


async def list_active_segment_llm_profiles(
    session: AsyncSession,
    *,
    locale: str = "ru",
) -> list[tuple[str, SegmentLLMProfile]]:
    """Return (segment_slug, profile_row) for active segments only."""
    locale = _normalize_profile_locale(locale)
    result = await session.execute(
        select(Segment.slug, SegmentLLMProfile)
        .join(Segment, Segment.id == SegmentLLMProfile.segment_id)
        .where(
            Segment.is_active.is_(True),
            SegmentLLMProfile.locale == locale,
        )
    )
    return [(slug, row) for slug, row in result.all()]


async def create_segment_llm_profile(
    session: AsyncSession,
    *,
    segment_id: int,
    target_lead: str,
    accept_examples: list[str],
    reject_examples: list[str],
    conflict_slugs: list[str],
    locale: str = "ru",
    requires_llm: bool = True,
    version: int = 1,
) -> SegmentLLMProfile:
    profile = SegmentLLMProfile(
        segment_id=segment_id,
        locale=_normalize_profile_locale(locale),
        target_lead=_validate_target_lead(target_lead),
        accept_examples=_validate_profile_string_list("accept_examples", accept_examples),
        reject_examples=_validate_profile_string_list("reject_examples", reject_examples),
        conflict_slugs=_validate_profile_string_list("conflict_slugs", conflict_slugs),
        requires_llm=bool(requires_llm),
        version=_validate_profile_version(version),
    )
    session.add(profile)
    await session.flush()
    return profile


async def update_segment_llm_profile(
    session: AsyncSession,
    *,
    profile_id: int,
    target_lead: str,
    accept_examples: list[str],
    reject_examples: list[str],
    conflict_slugs: list[str],
    requires_llm: bool | None = None,
) -> SegmentLLMProfile:
    result = await session.execute(
        select(SegmentLLMProfile).where(SegmentLLMProfile.id == profile_id)
    )
    profile = result.scalar_one()
    profile.target_lead = _validate_target_lead(target_lead)
    profile.accept_examples = _validate_profile_string_list(
        "accept_examples", accept_examples
    )
    profile.reject_examples = _validate_profile_string_list(
        "reject_examples", reject_examples
    )
    profile.conflict_slugs = _validate_profile_string_list(
        "conflict_slugs", conflict_slugs
    )
    if requires_llm is not None:
        profile.requires_llm = bool(requires_llm)
    profile.version = profile.version + 1
    await session.flush()
    return profile

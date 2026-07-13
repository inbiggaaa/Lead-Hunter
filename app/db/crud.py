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

# Гео-«без лимита» для pro-городов и business/trial. Реальный потолок — общий
# кап подписок business_hidden_cap_* (60), он же ограничивает число стран.
_GEO_UNLIMITED = 9999


def _plan_limits(plan: str) -> dict:
    """Матрица лимитов одного плана. business/trial → общий кап 60 (не БД-безлимит).
    Неизвестный план → free (least privilege). Free = start по гео."""
    from app.config import settings
    business = {
        "segments": settings.business_hidden_cap_segments,
        "channels": settings.business_hidden_cap_channels,
        "keywords": settings.business_hidden_cap_keywords,
        "countries": _GEO_UNLIMITED, "cities": _GEO_UNLIMITED,
    }
    matrix = {
        "free": {
            "segments": settings.max_segments_free, "channels": settings.max_channels_free,
            "keywords": settings.max_keywords_free, "countries": settings.max_countries_start,
            "cities": settings.max_cities_start,
        },
        "start": {
            "segments": settings.max_segments_start, "channels": settings.max_channels_start,
            "keywords": settings.max_keywords_start, "countries": settings.max_countries_start,
            "cities": settings.max_cities_start,
        },
        "pro": {
            "segments": settings.max_segments_pro, "channels": settings.max_channels_pro,
            "keywords": settings.max_keywords_pro, "countries": settings.max_countries_pro,
            "cities": _GEO_UNLIMITED,
        },
        "business": business, "trial": business,
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


def get_max_cities_per_sub(plan: str) -> int:
    return _plan_limits(plan)["cities"]


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


def cities_within_limit(plan: str, n_cities: int) -> bool:
    """Число городов в одной подписке не превышает лимит плана (тарифы v2, #81)."""
    return n_cities <= get_max_cities_per_sub(plan)


def countries_within_limit(plan: str, existing_country_ids, new_country_id: int) -> bool:
    """Добавление страны не выводит число distinct-стран за лимит плана.
    При утверждённых числах v2 обычно подчинён лимиту подписок (стран = сегментов),
    но защищает при их будущей смене через .env."""
    return len(set(existing_country_ids) | {new_country_id}) <= get_max_countries(plan)

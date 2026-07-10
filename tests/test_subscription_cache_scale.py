"""C5: кэш подписок — подготовка к масштабу.

1. rebuild_subscription_cache: четыре плоских SELECT + join в памяти вместо
   3 запросов на пользователя (N+1); пользователи без подписок и keywords
   в кэш не попадают. Формат записей не изменён.
2. _dispatch: сегментные словари и гео канала — in-memory (обновляются с
   reload keywords), на тёплых кэшах ни одного DB-запроса на матч.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.db.models import (
    Base, Category, City, Country, Keyword, Segment,
    SubscriptionCity, User, UserSubscription,
)
from app.userbot.poller import ChannelPoller


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key, value):
        self.store[key] = value

    async def expire(self, key, ttl):
        pass


# ── seed: 3 пользователя (подписка+города / только keyword / пустой) ──


@pytest_asyncio.fixture(loop_scope="function")
async def seed():
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        country = Country(slug="c5-country", name_ru="Тестляндия")
        category = Category(slug="c5-category")
        s.add_all([country, category])
        await s.flush()
        city = City(slug="c5-city", name_ru="Тестбург", country_id=country.id)
        segment = Segment(slug="c5-seg", category_id=category.id, title_ru="Тест")
        u_sub = User(telegram_id=95_000_001, language="ru", plan="free")
        u_kw = User(telegram_id=95_000_002, language="en", plan="pro")
        u_empty = User(telegram_id=95_000_003)
        s.add_all([city, segment, u_sub, u_kw, u_empty])
        await s.flush()
        sub = UserSubscription(
            user_id=u_sub.id, segment_id=segment.id,
            country_id=country.id, mode="cities",
        )
        kw = Keyword(user_id=u_kw.id, text="маникюр", is_active=True)
        s.add_all([sub, kw])
        await s.flush()
        s.add(SubscriptionCity(subscription_id=sub.id, city_id=city.id))
        await s.commit()
        ids = {
            "u_sub": u_sub.id, "u_kw": u_kw.id, "u_empty": u_empty.id,
            "segment_id": segment.id, "country_id": country.id, "city_id": city.id,
        }

    yield ids, engine, factory

    async with factory() as s:
        for uid in (ids["u_sub"], ids["u_kw"], ids["u_empty"]):
            await s.execute(delete(User).where(User.id == uid))
        await s.execute(delete(Segment).where(Segment.slug == "c5-seg"))
        await s.execute(delete(City).where(City.slug == "c5-city"))
        await s.execute(delete(Category).where(Category.slug == "c5-category"))
        await s.execute(delete(Country).where(Country.slug == "c5-country"))
        await s.commit()
    await engine.dispose()


async def _rebuild_with(factory, fake_redis):
    from app.cache import subscription_cache as sc

    with patch.object(sc, "async_session_factory", factory), \
         patch.object(sc, "get_redis", new=AsyncMock(return_value=fake_redis)):
        await sc.rebuild_subscription_cache("c5_chat")
    return json.loads(fake_redis.store["sub:by_chat:c5_chat"])


async def test_rebuild_format_unchanged_and_empty_users_dropped(seed):
    """Формат записей тот же; пользователь без подписок/keywords не кэшируется."""
    ids, engine, factory = seed
    data = await _rebuild_with(factory, _FakeRedis())

    by_uid = {u["user_id"]: u for u in data}
    assert ids["u_empty"] not in by_uid  # C5: пустые не кэшируются

    u_sub = by_uid[ids["u_sub"]]
    assert set(u_sub.keys()) == {
        "user_id", "telegram_id", "lang", "plan", "subscriptions", "keyword_texts",
    }
    assert u_sub["subscriptions"] == [{
        "segment_id": ids["segment_id"],
        "country_id": ids["country_id"],
        "city_ids": [ids["city_id"]],
    }]
    assert u_sub["keyword_texts"] == []

    u_kw = by_uid[ids["u_kw"]]
    assert u_kw["subscriptions"] == []
    assert u_kw["keyword_texts"] == ["маникюр"]
    assert u_kw["plan"] == "pro"


async def test_rebuild_fixed_query_count(seed):
    """N+1 устранён: число SELECT не зависит от числа пользователей."""
    ids, engine, factory = seed
    statements: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    try:
        await _rebuild_with(factory, _FakeRedis())
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _count)

    # users + user_subscriptions + keywords + subscription_cities = 4
    assert len(statements) == 4


# ── _dispatch: ноль DB-запросов на тёплых кэшах ──


async def test_dispatch_warm_caches_no_db():
    """С прогретыми _seg_by_slug/_seg_info/_channel_geo диспатч не ходит в БД."""
    poller = ChannelPoller()
    poller._seg_by_slug = {"c5-seg": 42}
    poller._seg_info = {"c5-seg": {"emoji": "✨", "ru": "Тест", "en": "Test"}}
    poller._channel_geo["c5_chat"] = (7, {3}, True)

    users = [{
        "user_id": 1, "telegram_id": 95_000_001, "lang": "ru", "plan": "free",
        "subscriptions": [{"segment_id": 42, "country_id": 7, "city_ids": []}],
        "keyword_texts": [],
    }]
    sent: list[dict] = []

    async def _push(payload):
        sent.append(payload)

    def _no_db(*args, **kwargs):
        raise AssertionError("DB must not be touched on warm caches")

    with patch("app.cache.subscription_cache.get_interested_users",
               new=AsyncMock(return_value=users)), \
         patch("app.cache.subscription_cache.push_notification", new=_push), \
         patch("app.cache.subscription_cache.rebuild_subscription_cache",
               new=AsyncMock()), \
         patch("app.userbot.poller.async_session_factory", new=_no_db):
        await poller._dispatch(
            chat_username="c5_chat", message_text="нужен тест",
            message_id=1, matched_segments=["c5-seg"],
            is_urgent=False, sender=None,
        )

    assert len(sent) == 1
    assert sent[0]["matched_segments"] == [{"emoji": "✨", "title": "Тест"}]


async def test_geo_memo_cleared_on_seg_maps_refresh():
    """Гео-мемо живёт не дольше reload'а keywords."""
    poller = ChannelPoller()
    poller._channel_geo["stale_chat"] = (1, set(), True)
    poller._set_seg_maps([])
    assert poller._channel_geo == {}

"""Tests for «Вариант Б» — personal keywords + watched channels (task A1, fable_audit.md).

Spec (CLAUDE.md §5а): «Личные keywords работают всегда, независимо от classifier».
Bug C1 (audit 09.07.2026): three sequential blockers made Вариант Б dead end-to-end:
1. _poll_channel dispatched only segment-matched messages;
2. _dispatch checked personal keywords only inside the subscription loop
   (no subscriptions → no keyword check) and only under geo filters;
3. non-catalog channels have country=None → geo filter rejected every subscription.

T1/T2/T4/T5 are integration tests against the throwaway test DB (see recipe in
fable_audit.md task 0.3). T3 is a mock-based unit test for _poll_channel.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from telethon.tl.types import Message

from app.config import settings
from app.db.models import Base, Category, CatalogChannel, Country, Segment
from app.userbot.poller import ChannelPoller

GEO_CHAT = "vb_test_geo_chat"
NO_CATALOG_CHAT = "vb_test_private_chat"


# ── committed seed data (dispatch reads via its own sessions) ──


@pytest_asyncio.fixture(loop_scope="function")
async def seed():
    """Insert committed Country/Category/Segment/CatalogChannel rows, clean up after.

    Yields (ids, session_factory). The factory is bound to THIS test's event
    loop — tests patch app.userbot.poller.async_session_factory with it,
    because the global factory's pooled connections break across pytest's
    function-scoped event loops ("Event loop is closed").
    """
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        country = Country(slug="vb-test-country", name_ru="Тестляндия")
        category = Category(slug="vb-test-category")
        s.add_all([country, category])
        await s.flush()
        segment = Segment(slug="vb-manicure", category_id=category.id, title_ru="Маникюр")
        s.add(segment)
        await s.flush()
        channel = CatalogChannel(
            chat_username=GEO_CHAT, title="Test geo chat",
            auto_matched_country_id=country.id,
        )
        s.add(channel)
        await s.commit()
        ids = {
            "country_id": country.id,
            "segment_id": segment.id,
            "segment_slug": segment.slug,
        }

    yield ids, factory

    async with factory() as s:
        await s.execute(delete(CatalogChannel).where(CatalogChannel.chat_username == GEO_CHAT))
        await s.execute(delete(Segment).where(Segment.slug == "vb-manicure"))
        await s.execute(delete(Category).where(Category.slug == "vb-test-category"))
        await s.execute(delete(Country).where(Country.slug == "vb-test-country"))
        await s.commit()
    await engine.dispose()


def _user(user_id: int, subscriptions: list, keywords: list[str]) -> dict:
    return {
        "user_id": user_id,
        "telegram_id": 9_000_000 + user_id,
        "lang": "ru",
        "plan": "free",
        "subscriptions": subscriptions,
        "keyword_texts": keywords,
    }


def _dispatch_patches(users: list[dict]):
    """Patch cache functions used inside _dispatch. Returns (ctx-managers, sent-list)."""
    sent: list[dict] = []

    async def _push(payload):
        sent.append(payload)

    patches = [
        patch(
            "app.cache.subscription_cache.get_interested_users",
            new=AsyncMock(return_value=users),
        ),
        patch("app.cache.subscription_cache.push_notification", new=_push),
        patch(
            "app.cache.subscription_cache.rebuild_subscription_cache",
            new=AsyncMock(),
        ),
    ]
    return patches, sent


async def _run_dispatch(users, chat, text, segments, session_factory):
    patches, sent = _dispatch_patches(users)
    patches.append(
        patch("app.userbot.poller.async_session_factory", new=session_factory)
    )
    for p in patches:
        p.start()
    try:
        poller = ChannelPoller()
        await poller._dispatch(
            chat_username=chat, message_text=text, message_id=101,
            matched_segments=segments, is_urgent=False, sender=None,
        )
    finally:
        for p in patches:
            p.stop()
    return sent


# ═══ T1: keyword user WITHOUT subscriptions, catalog channel ═══


async def test_t1_keyword_without_subscriptions_catalog_channel(seed):
    """Личный keyword работает у пользователя без единой подписки."""
    ids, factory = seed
    users = [_user(1, subscriptions=[], keywords=["маникюр"])]
    sent = await _run_dispatch(
        users, GEO_CHAT, "Нужен маникюр в центре, посоветуйте мастера", segments=[], session_factory=factory,
    )
    assert len(sent) == 1
    assert sent[0]["user_id"] == 1
    assert sent[0]["matched_segments"][0]["emoji"] == "🔑"


# ═══ T2: keyword user, watched channel NOT in catalog (country=None) ═══


async def test_t2_keyword_non_catalog_channel(seed):
    """Keyword-матч в своём канале вне каталога (нет гео-данных)."""
    ids, factory = seed
    users = [_user(
        2,
        subscriptions=[{"segment_id": ids["segment_id"],
                        "country_id": ids["country_id"], "city_ids": []}],
        keywords=["фотограф"],
    )]
    sent = await _run_dispatch(
        users, NO_CATALOG_CHAT, "Ищем фотографа на свадьбу", segments=[], session_factory=factory,
    )
    assert len(sent) == 1
    assert sent[0]["user_id"] == 2


# ═══ T3: _poll_channel lets keyword-only messages reach dispatch queue ═══


async def test_t3_poll_channel_queues_keyword_only_message():
    """Сообщение без сегмент-матча, но с личным keyword → в очередь на dispatch."""
    poller = ChannelPoller()
    poller._keyword_map = {
        "vb-manicure": {"demand": ["полностью нерелевантная фраза"], "stop": [], "synonym": []},
    }
    poller._universal_stops = []
    poller._domain_word_map = {}
    poller._channel_segments = {}
    poller._personal_keywords = ["маникюр"]  # loaded by _load_personal_keywords in prod

    entity = MagicMock()
    entity.broadcast = False
    entity.megagroup = True
    entity.title = None
    entity.participants_count = None

    msg = MagicMock(spec=Message)
    msg.id = 5
    msg.message = "Девочки, кто делает маникюр в нашем районе?"
    msg.date = datetime.now(timezone.utc)
    msg.sender = None

    account = MagicMock()
    account.account_id = 1

    with patch.object(poller, "_resolve_entity", new=AsyncMock(return_value=entity)), \
         patch.object(poller, "_fetch_all_since", new=AsyncMock(return_value=[msg])), \
         patch.object(poller, "_get_cursor", new=AsyncMock(return_value=0)), \
         patch.object(poller, "_set_cursor", new=AsyncMock()), \
         patch.object(ChannelPoller, "_log_unmatched", new=AsyncMock()):
        await poller._poll_channel(account, "vb_test_chat", tier_name="Hot")

    assert len(poller._pending_matches) == 1
    m = poller._pending_matches[0]
    assert m.keyword_only is True
    assert m.candidate_segments == []
    assert m.skip_llm is True  # личные keywords минуют LLM по спеке


# ═══ T4: regression — segment match with geo filtering unchanged ═══


async def test_t4_segment_geo_matching_regression(seed):
    """Сегмент-матч с гео-фильтром работает как раньше (позитив + негатив)."""
    ids, factory = seed
    users = [
        _user(3, subscriptions=[{"segment_id": ids["segment_id"],
                                 "country_id": ids["country_id"], "city_ids": []}],
              keywords=[]),
        _user(4, subscriptions=[{"segment_id": ids["segment_id"],
                                 "country_id": ids["country_id"] + 999, "city_ids": []}],
              keywords=[]),
    ]
    sent = await _run_dispatch(
        users, GEO_CHAT, "Нужен маникюр срочно", segments=[ids["segment_slug"]], session_factory=factory,
    )
    assert [p["user_id"] for p in sent] == [3]


# ═══ T5: word-boundary for personal keywords (A1.4) ═══


async def test_t5_keyword_word_boundary(seed):
    """«кот» не матчит «который»; «маникюр» матчит «Маникюр!»."""
    ids, factory = seed
    users = [_user(5, subscriptions=[], keywords=["кот"])]
    sent = await _run_dispatch(
        users, NO_CATALOG_CHAT, "Который час в Ханое?", segments=[], session_factory=factory,
    )
    assert sent == []

    users = [_user(6, subscriptions=[], keywords=["маникюр"])]
    sent = await _run_dispatch(
        users, NO_CATALOG_CHAT, "Маникюр! Кто может завтра утром?", segments=[], session_factory=factory,
    )
    assert len(sent) == 1

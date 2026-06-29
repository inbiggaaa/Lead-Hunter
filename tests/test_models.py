"""Unit tests for database models."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    User,
    Keyword,
    Country,
    City,
    Segment,
    SegmentKeyword,
    UserSubscription,
    SentLog,
    WatchedChat,
)

pytestmark = pytest.mark.asyncio


class TestUserModel:
    async def test_create_user(self, session):
        user = User(telegram_id=12345, username="testuser", language="ru")
        session.add(user)
        await session.flush()

        assert user.id is not None
        assert user.telegram_id == 12345
        assert user.username == "testuser"
        assert user.language == "ru"
        assert user.plan == "free"
        assert user.onboarded is False
        assert user.is_banned is False

    async def test_telegram_id_unique(self, session):
        session.add(User(telegram_id=11111))
        await session.flush()

        session.add(User(telegram_id=11111))
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_default_values(self, session):
        user = User(telegram_id=99999)
        session.add(user)
        await session.flush()

        assert user.plan == "free"
        assert user.language == "ru"
        assert user.is_banned is False
        assert user.onboarded is False
        assert user.source == "direct"


class TestKeywordModel:
    async def test_create_keyword(self, session):
        user = User(telegram_id=20001)
        session.add(user)
        await session.flush()

        kw = Keyword(user_id=user.id, text="ищу повара")
        session.add(kw)
        await session.flush()

        assert kw.id is not None
        assert kw.text == "ищу повара"
        assert kw.is_active is True
        assert kw.is_regex is False

    async def test_keyword_cascade_on_user_delete(self, session):
        user = User(telegram_id=30001)
        session.add(user)
        await session.flush()

        kw = Keyword(user_id=user.id, text="нужен байк")
        session.add(kw)
        await session.flush()

        kw_id = kw.id
        await session.delete(user)
        await session.flush()

        result = await session.execute(select(Keyword).where(Keyword.id == kw_id))
        assert result.scalar_one_or_none() is None


class TestSentLogModel:
    async def test_unique_user_message_hash(self, session):
        user = User(telegram_id=40001)
        session.add(user)
        await session.flush()

        log1 = SentLog(user_id=user.id, message_hash="abc123")
        session.add(log1)
        await session.flush()

        log2 = SentLog(user_id=user.id, message_hash="abc123")
        session.add(log2)
        with pytest.raises(IntegrityError):
            await session.flush()


class TestCountryModel:
    async def test_create_country(self, session):
        country = Country(slug="test-vn", name_ru="Тест", name_en="Test")
        session.add(country)
        await session.flush()

        assert country.id is not None
        assert country.slug == "test-vn"
        assert country.is_active is True

    async def test_slug_unique(self, session):
        session.add(Country(slug="unique-test"))
        await session.flush()

        session.add(Country(slug="unique-test"))
        with pytest.raises(IntegrityError):
            await session.flush()


class TestCityModel:
    async def test_create_city(self, session):
        country = Country(slug="city-test", name_ru="Страна", name_en="Country")
        session.add(country)
        await session.flush()

        city = City(slug="city-nhatrang", name_ru="Нячанг", name_en="Nha Trang", country_id=country.id)
        session.add(city)
        await session.flush()

        assert city.id is not None
        assert city.country_id == country.id

    async def test_city_requires_country(self, session):
        city = City(slug="orphan", name_ru="Без страны", country_id=999999)
        session.add(city)
        with pytest.raises(IntegrityError):
            await session.flush()


class TestSegmentModel:
    async def test_create_segment(self, session):
        seg = Segment(slug="test-catering", title_ru="Кейтеринг", title_en="Catering", emoji="🍜", sort_order=1)
        session.add(seg)
        await session.flush()

        assert seg.id is not None
        assert seg.slug == "test-catering"
        assert seg.emoji == "🍜"

    async def test_segment_keywords_relationship(self, session):
        seg = Segment(slug="test-seg", title_ru="Тест", title_en="Test")
        session.add(seg)
        await session.flush()

        kw1 = SegmentKeyword(segment_id=seg.id, text="demand phrase", keyword_type="demand")
        kw2 = SegmentKeyword(segment_id=seg.id, text="stop phrase", keyword_type="stop")
        session.add_all([kw1, kw2])
        await session.flush()

        result = await session.execute(
            select(SegmentKeyword).where(SegmentKeyword.segment_id == seg.id)
        )
        keywords = result.scalars().all()
        assert len(keywords) == 2


class TestUserSubscriptionModel:
    async def test_create_subscription(self, session):
        user = User(telegram_id=50001)
        seg = Segment(slug="sub-test", title_ru="Тест", title_en="Test")
        country = Country(slug="sub-country", name_ru="Страна", name_en="Country")
        session.add_all([user, seg, country])
        await session.flush()

        sub = UserSubscription(
            user_id=user.id, segment_id=seg.id, country_id=country.id, mode="all"
        )
        session.add(sub)
        await session.flush()

        assert sub.id is not None
        assert sub.mode == "all"

    async def test_unique_user_segment_country(self, session):
        user = User(telegram_id=60001)
        seg = Segment(slug="unique-test", title_ru="Уник", title_en="Unique")
        country = Country(slug="unique-country", name_ru="Уник", name_en="Unique")
        session.add_all([user, seg, country])
        await session.flush()

        sub1 = UserSubscription(user_id=user.id, segment_id=seg.id, country_id=country.id)
        session.add(sub1)
        await session.flush()

        sub2 = UserSubscription(user_id=user.id, segment_id=seg.id, country_id=country.id)
        session.add(sub2)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_idx_user_sub_lookup_exists(self, session):
        """Verify the index idx_user_sub_lookup is created."""
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'user_subscriptions' AND indexname = 'idx_user_sub_lookup'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None, "Index idx_user_sub_lookup not found"


class TestWatchedChatModel:
    async def test_create_watched_chat(self, session):
        user = User(telegram_id=70001)
        session.add(user)
        await session.flush()

        chat = WatchedChat(
            user_id=user.id,
            chat_username="test_channel",
            source="manual",
            status="approved",
        )
        session.add(chat)
        await session.flush()

        assert chat.id is not None
        assert chat.status == "approved"
        assert chat.is_private is False

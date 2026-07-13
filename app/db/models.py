import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── users ──

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(10), default="ru")
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    plan_expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    suspended_until: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_blocked_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_bot_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="direct")
    admin_note: Mapped[str | None] = mapped_column(Text)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── subscriptions ──

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    payment_method: Mapped[str] = mapped_column(String(20))
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    invoice_id: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[float | None] = mapped_column()
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── keywords ──

class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── watched_chats ──

class WatchedChat(Base):
    __tablename__ = "watched_chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chat_username: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(20))
    userbot_account_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="approved")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False)
    country_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("countries.id", ondelete="SET NULL"), nullable=True
    )
    city_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── sent_log ──

class SentLog(Base):
    __tablename__ = "sent_log"
    __table_args__ = (
        UniqueConstraint("user_id", "message_hash"),
        Index("idx_sent_log_content_dedup", "user_id", "content_hash", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── countries ──

class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name_ru: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    cities: Mapped[list["City"]] = relationship(back_populates="country")


# ── cities ──

class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("country_id", "slug", name="uq_cities_country_slug"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name_ru: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    country_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    country: Mapped["Country"] = relationship(back_populates="cities")


# ── categories ──

class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    title_ru: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    emoji: Mapped[str | None] = mapped_column(String(8))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    segments: Mapped[list["Segment"]] = relationship(back_populates="category")


# ── segments ──

class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    title_ru: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    emoji: Mapped[str | None] = mapped_column(String(8))
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # A3 (quarantine01): карантин — сегмент матчится и логируется в
    # llm_decisions (датасет), но НЕ диспатчится пользователям
    is_quarantined: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Who the lead is / what shape their message has (B4, migration lead_direction01):
    #   'demand' — лид ищет услугу («ищу мастера»); Pass 3 активен
    #   'buy'    — лид покупает/снимает с бюджетом+контактом («куплю авто»,
    #              «сниму квартиру») — Pass 3 пропускается
    #   'supply' — лид продаёт («продам байк» + цена/доки) — Pass 3
    #              пропускается И DEMAND/OFFER инвертируется в LLM-промпте
    lead_direction: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="demand"
    )

    keywords: Mapped[list["SegmentKeyword"]] = relationship(back_populates="segment")
    category: Mapped["Category"] = relationship(back_populates="segments")


# ── segment_keywords ──

class SegmentKeyword(Base):
    __tablename__ = "segment_keywords"
    __table_args__ = (UniqueConstraint("segment_id", "text", "keyword_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    segment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("segments.id", ondelete="CASCADE")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    keyword_type: Mapped[str] = mapped_column(String(20), default="demand")
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    segment: Mapped["Segment"] = relationship(back_populates="keywords")


# ── catalog_channels ──

class CatalogChannel(Base):
    __tablename__ = "catalog_channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_username: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[int | None] = mapped_column(Integer)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    manually_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)
    auto_matched_country_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("countries.id", ondelete="SET NULL")
    )
    auto_matched_city_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="SET NULL")
    )
    # Привязка к аккаунту-участнику для приватных -100…-чатов (NULL = любой аккаунт)
    userbot_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── channel_segments ──

class ChannelSegment(Base):
    __tablename__ = "channel_segments"

    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog_channels.id", ondelete="CASCADE"), primary_key=True
    )
    segment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("segments.id", ondelete="CASCADE"), primary_key=True
    )


# ── channel_cities ──

class ChannelCity(Base):
    __tablename__ = "channel_cities"

    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("catalog_channels.id", ondelete="CASCADE"), primary_key=True
    )
    city_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True
    )


# ── user_subscriptions ──

class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "segment_id", "country_id"),
        Index("idx_user_sub_lookup", "segment_id", "country_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    segment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False
    )
    country_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(10), default="all")
    subscribed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── subscription_cities ──

class SubscriptionCity(Base):
    __tablename__ = "subscription_cities"

    subscription_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    city_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True
    )


# ── discovered_chats ──

class DiscoveredChat(Base):
    __tablename__ = "discovered_chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_username: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    participants: Mapped[int | None] = mapped_column(Integer)
    auto_matched_country_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("countries.id", ondelete="SET NULL")
    )
    auto_matched_city_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cities.id", ondelete="SET NULL")
    )
    discovered_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── referrals ──

class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referral_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    bonus_days: Mapped[int] = mapped_column(Integer, default=7)
    referral_trial_bonus: Mapped[int] = mapped_column(Integer, default=3)
    activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── support_messages ──

class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── user_ignores ──

class UserIgnore(Base):
    __tablename__ = "user_ignores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ── reminders ──

class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)


# ── periodic_prefs ──

class PeriodicPref(Base):
    __tablename__ = "periodic_prefs"
    __table_args__ = (
        CheckConstraint(
            "msg_type IN ('weekly_digest', 'niche_growth', 'monthly_summary')",
            name="ck_periodic_prefs_msg_type",
        ),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    msg_type: Mapped[str] = mapped_column(String(30), primary_key=True, nullable=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))


# ── llm_decisions ──

class LLMDecision(Base):
    """Every LLM validation call — for shadow monitoring and future fine-tune dataset."""
    __tablename__ = "llm_decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chat_username: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_text_masked: Mapped[str] = mapped_column(Text, nullable=False)
    rule_segments: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    llm_verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    llm_segments: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    llm_reason: Mapped[str | None] = mapped_column(Text)
    certainty: Mapped[str | None] = mapped_column(String(10))
    llm_mode: Mapped[str] = mapped_column(String(10), default="shadow")
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_llm_decisions_created", "created_at"),
        Index("idx_llm_decisions_chat_msg", "chat_username", "message_id"),
    )


# ── feedback ──

class Feedback(Base):
    """User feedback on notifications — gold labels for fine-tune."""
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    chat_username: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(15), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_feedback_chat_msg", "chat_username", "message_id"),
    )

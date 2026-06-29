"""SQLAdmin model views for all catalog and user models."""

from sqladmin import ModelView

from app.db.models import (
    User,
    Subscription,
    Keyword,
    WatchedChat,
    SentLog,
    Country,
    City,
    Segment,
    SegmentKeyword,
    CatalogChannel,
    ChannelSegment,
    ChannelCity,
    UserSubscription,
    SubscriptionCity,
    DiscoveredChat,
    Referral,
    SupportMessage,
    UserIgnore,
    Reminder,
    PeriodicPref,
)


# ── Users & subscriptions ──

class UserAdmin(ModelView, model=User):
    column_list = [
        User.id, User.telegram_id, User.username, User.language,
        User.plan, User.onboarded, User.is_banned, User.source, User.created_at,
    ]
    column_searchable_list = [User.username, User.telegram_id]
    column_sortable_list = [User.id, User.created_at, User.plan]
    can_create = True
    can_edit = True
    can_delete = True
    name = "Пользователь"
    name_plural = "👥 Пользователи"


class SubscriptionAdmin(ModelView, model=Subscription):
    column_list = [
        Subscription.id, Subscription.user_id, Subscription.plan,
        Subscription.period, Subscription.payment_status, Subscription.amount,
        Subscription.created_at,
    ]
    name = "Подписка"
    name_plural = "💰 Подписки"


# ── Keywords & channels ──

class KeywordAdmin(ModelView, model=Keyword):
    column_list = [Keyword.id, Keyword.user_id, Keyword.text, Keyword.is_regex, Keyword.is_active]
    name = "Ключевое слово"
    name_plural = "⚙️ Ключевые слова"


class WatchedChatAdmin(ModelView, model=WatchedChat):
    column_list = [
        WatchedChat.id, WatchedChat.user_id, WatchedChat.chat_username,
        WatchedChat.status, WatchedChat.is_private, WatchedChat.created_at,
    ]
    name = "Канал"
    name_plural = "📢 Каналы пользователей"


# ── Sent log ──

class SentLogAdmin(ModelView, model=SentLog):
    column_list = [SentLog.id, SentLog.user_id, SentLog.message_hash, SentLog.is_urgent, SentLog.sent_at]
    name = "Отправленное"
    name_plural = "📤 Sent log"


# ── Catalog: countries, cities ──

class CountryAdmin(ModelView, model=Country):
    column_list = [Country.id, Country.slug, Country.name_ru, Country.name_en, Country.is_active]
    name = "Страна"
    name_plural = "🌍 Страны"


class CityAdmin(ModelView, model=City):
    column_list = [City.id, City.slug, City.name_ru, City.name_en, City.country_id, City.is_active]
    name = "Город"
    name_plural = "🏙 Города"


# ── Catalog: segments ──

class SegmentAdmin(ModelView, model=Segment):
    column_list = [Segment.id, Segment.slug, Segment.emoji, Segment.title_ru, Segment.title_en, Segment.sort_order, Segment.is_active]
    name = "Направление"
    name_plural = "📌 Направления"


class SegmentKeywordAdmin(ModelView, model=SegmentKeyword):
    column_list = [
        SegmentKeyword.id, SegmentKeyword.segment_id, SegmentKeyword.text,
        SegmentKeyword.keyword_type, SegmentKeyword.is_active,
    ]
    name = "Keyword направления"
    name_plural = "🏷 Keywords направлений"


# ── Catalog: channels ──

class CatalogChannelAdmin(ModelView, model=CatalogChannel):
    column_list = [
        CatalogChannel.id, CatalogChannel.chat_username, CatalogChannel.title,
        CatalogChannel.participants, CatalogChannel.is_verified,
        CatalogChannel.auto_matched_country_id, CatalogChannel.auto_matched_city_id,
    ]
    name = "Канал каталога"
    name_plural = "📋 Каталог каналов"


class ChannelSegmentAdmin(ModelView, model=ChannelSegment):
    column_list = [ChannelSegment.channel_id, ChannelSegment.segment_id]
    name = "Channel×Segment"
    name_plural = "🔗 Channel×Segment"


class ChannelCityAdmin(ModelView, model=ChannelCity):
    column_list = [ChannelCity.channel_id, ChannelCity.city_id]
    name = "Channel×City"
    name_plural = "🔗 Channel×City"


# ── User subscriptions ──

class UserSubscriptionAdmin(ModelView, model=UserSubscription):
    column_list = [
        UserSubscription.id, UserSubscription.user_id,
        UserSubscription.segment_id, UserSubscription.country_id,
        UserSubscription.mode, UserSubscription.subscribed_at,
    ]
    name = "Подписка пользователя"
    name_plural = "📋 Подписки пользователей"


class SubscriptionCityAdmin(ModelView, model=SubscriptionCity):
    column_list = [SubscriptionCity.subscription_id, SubscriptionCity.city_id]
    name = "Город подписки"
    name_plural = "🏙 Города подписок"


# ── Discovered chats ──

class DiscoveredChatAdmin(ModelView, model=DiscoveredChat):
    column_list = [
        DiscoveredChat.id, DiscoveredChat.chat_username, DiscoveredChat.title,
        DiscoveredChat.participants, DiscoveredChat.discovered_at,
    ]
    name = "Найденный чат"
    name_plural = "🔍 Найденные чаты"


# ── Referrals ──

class ReferralAdmin(ModelView, model=Referral):
    column_list = [
        Referral.id, Referral.referrer_id, Referral.referral_id,
        Referral.ref_code, Referral.status, Referral.created_at,
    ]
    name = "Реферал"
    name_plural = "🎁 Рефералы"


# ── Support ──

class SupportMessageAdmin(ModelView, model=SupportMessage):
    column_list = [
        SupportMessage.id, SupportMessage.user_id, SupportMessage.direction,
        SupportMessage.is_read, SupportMessage.created_at,
    ]
    name = "Сообщение саппорта"
    name_plural = "💬 Чат поддержки"


# ── Ignores ──

class UserIgnoreAdmin(ModelView, model=UserIgnore):
    column_list = [UserIgnore.id, UserIgnore.user_id, UserIgnore.type, UserIgnore.value]
    name = "Игнор"
    name_plural = "🚫 Игнор-лист"


# ── Reminders ──

class ReminderAdmin(ModelView, model=Reminder):
    column_list = [
        Reminder.id, Reminder.user_id, Reminder.type,
        Reminder.day_number, Reminder.is_disabled,
    ]
    name = "Напоминание"
    name_plural = "⏰ Напоминания"


# ── Periodic prefs ──

class PeriodicPrefAdmin(ModelView, model=PeriodicPref):
    column_list = [PeriodicPref.user_id, PeriodicPref.msg_type, PeriodicPref.is_disabled]
    name = "Период. настройка"
    name_plural = "📊 Периодические настройки"

"""FastAPI + SQLAdmin admin panel. Runs on 127.0.0.1:8001."""

import uvicorn
from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy import create_engine

from app.config import settings
from app.db.models import Base
from app.admin.auth import AdminAuth
from app.admin.views import (
    UserAdmin,
    SubscriptionAdmin,
    KeywordAdmin,
    WatchedChatAdmin,
    SentLogAdmin,
    CountryAdmin,
    CityAdmin,
    SegmentAdmin,
    SegmentKeywordAdmin,
    CatalogChannelAdmin,
    ChannelSegmentAdmin,
    ChannelCityAdmin,
    UserSubscriptionAdmin,
    SubscriptionCityAdmin,
    DiscoveredChatAdmin,
    ReferralAdmin,
    SupportMessageAdmin,
    UserIgnoreAdmin,
    ReminderAdmin,
    PeriodicPrefAdmin,
)


def create_app() -> FastAPI:
    app = FastAPI(title="LeadHunter Admin")

    # Sync engine for SQLAdmin
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)

    # Create tables if not exist
    Base.metadata.create_all(engine)

    # Auth
    auth_backend = AdminAuth(secret_key=settings.admin_secret or "dev-secret")

    # Admin
    admin = Admin(app, engine, authentication_backend=auth_backend, title="LeadHunter Admin")

    # Register views
    admin.add_view(UserAdmin)
    admin.add_view(SubscriptionAdmin)
    admin.add_view(KeywordAdmin)
    admin.add_view(WatchedChatAdmin)
    admin.add_view(SentLogAdmin)
    admin.add_view(CountryAdmin)
    admin.add_view(CityAdmin)
    admin.add_view(SegmentAdmin)
    admin.add_view(SegmentKeywordAdmin)
    admin.add_view(CatalogChannelAdmin)
    admin.add_view(ChannelSegmentAdmin)
    admin.add_view(ChannelCityAdmin)
    admin.add_view(UserSubscriptionAdmin)
    admin.add_view(SubscriptionCityAdmin)
    admin.add_view(DiscoveredChatAdmin)
    admin.add_view(ReferralAdmin)
    admin.add_view(SupportMessageAdmin)
    admin.add_view(UserIgnoreAdmin)
    admin.add_view(ReminderAdmin)
    admin.add_view(PeriodicPrefAdmin)

    return app


def main():
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    main()

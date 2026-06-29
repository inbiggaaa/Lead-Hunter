"""FastAPI + SQLAdmin admin panel. Runs on 127.0.0.1:8001."""


import uvicorn
from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy import create_engine

from app.config import settings
from app.db.models import Base
from app.admin.auth import AdminAuth
from app.admin.views import (
    UserAdmin, SubscriptionAdmin, KeywordAdmin, WatchedChatAdmin, SentLogAdmin,
    CountryAdmin, CityAdmin, SegmentAdmin, SegmentKeywordAdmin, CatalogChannelAdmin,
    ChannelSegmentAdmin, ChannelCityAdmin, UserSubscriptionAdmin, SubscriptionCityAdmin,
    DiscoveredChatAdmin, ReferralAdmin, SupportMessageAdmin, UserIgnoreAdmin,
    ReminderAdmin, PeriodicPrefAdmin,
)

from app.admin.nav import NavView, NavChatView

VIEWS = [
    NavView, NavChatView,
    CountryAdmin, CityAdmin, SegmentAdmin, SegmentKeywordAdmin, CatalogChannelAdmin,
    ChannelSegmentAdmin, ChannelCityAdmin, UserSubscriptionAdmin, SubscriptionCityAdmin,
    DiscoveredChatAdmin, ReferralAdmin, SupportMessageAdmin, UserIgnoreAdmin,
    ReminderAdmin, PeriodicPrefAdmin,
]


def create_app() -> FastAPI:
    app = FastAPI(title="LeadHunter Admin")

    # Sync engine for SQLAdmin
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)

    # Auth + Admin
    auth_backend = AdminAuth(secret_key=settings.admin_secret or "dev-secret")
    admin = Admin(app, engine, authentication_backend=auth_backend, title="LeadHunter Admin")

    for view in VIEWS:
        admin.add_view(view)

    return app


def main():
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    main()

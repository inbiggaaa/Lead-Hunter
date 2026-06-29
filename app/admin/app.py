"""FastAPI admin panel — REST API + SPA static + SQLAdmin (legacy).

Runs on 0.0.0.0:8001.
SPA routes:    /                    → static index.html (catch-all)
API routes:    /api/*               → REST endpoints (session auth)
SQLAdmin:      /admin/*             → SQLAdmin (legacy, self-auth)
Chat WS:       /api/chat/ws         → WebSocket
"""

import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqladmin import Admin
from sqlalchemy import create_engine
from starlette.responses import Response

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
from app.admin.api import api_router

VIEWS = [
    NavView, NavChatView,
    CountryAdmin, CityAdmin, SegmentAdmin, SegmentKeywordAdmin, CatalogChannelAdmin,
    ChannelSegmentAdmin, ChannelCityAdmin, UserSubscriptionAdmin, SubscriptionCityAdmin,
    DiscoveredChatAdmin, ReferralAdmin, SupportMessageAdmin, UserIgnoreAdmin,
    ReminderAdmin, PeriodicPrefAdmin,
]

# Path to the built SPA
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app() -> FastAPI:
    app = FastAPI(title="LeadHunter Admin")

    # ── Session middleware (for SPA auth) ──
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_secret or "dev-secret",
    )

    # ── Auth middleware for /api/* routes ──
    @app.middleware("http")
    async def api_auth_middleware(request: Request, call_next):
        if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/auth/"):
            if not request.session.get("authenticated"):
                if request.url.path.startswith("/api/chat/ws"):
                    # WebSocket — handled in endpoint
                    pass
                else:
                    return Response(status_code=401, content='{"detail":"Not authenticated"}',
                                    media_type="application/json")
        response = await call_next(request)
        return response

    # ── Sync engine for SQLAdmin ──
    sync_url = settings.database_url.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    Base.metadata.create_all(engine)

    # ── SQLAdmin (legacy) ──
    auth_backend = AdminAuth(secret_key=settings.admin_secret or "dev-secret")
    admin = Admin(app, engine, authentication_backend=auth_backend, title="LeadHunter Admin")
    for view in VIEWS:
        admin.add_view(view)

    # ── REST API ──
    app.include_router(api_router)

    # ── SPA static files (if built) ──
    if os.path.isdir(STATIC_DIR):
        app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve SPA index.html for all non-api, non-admin routes."""
            if full_path.startswith("api/") or full_path.startswith("admin/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            index = os.path.join(STATIC_DIR, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
            raise HTTPException(status_code=404)

    return app


def main():
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    main()

"""FastAPI admin panel — REST API + SPA static.

Runs on 0.0.0.0:8001.
SPA routes:    /                    → static index.html (catch-all)
API routes:    /api/*               → REST endpoints (session auth)
Chat WS:       /api/chat/ws         → WebSocket
"""

import os
import secrets

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.admin.api import api_router

# Path to the built SPA
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _generate_secret() -> str:
    """Generate a random session secret at startup if ADMIN_SECRET is not set."""
    import logging
    logging.getLogger(__name__).warning(
        "ADMIN_SECRET not set — using randomly generated key. "
        "Sessions will be invalidated on restart."
    )
    return secrets.token_hex(32)


def create_app() -> FastAPI:
    app = FastAPI(title="LeadHunter Admin")

    # ── Session middleware (for SPA auth) ──
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_secret or _generate_secret(),
    )

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

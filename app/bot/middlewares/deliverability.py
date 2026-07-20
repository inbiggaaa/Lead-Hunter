"""Bot middleware: refuse banned / actively suspended users early."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from app.cache.subscription_cache import user_is_deliverable
from app.db.crud import get_user
from app.db.session import get_session


class DeliverabilityMiddleware(BaseMiddleware):
    """Drop updates from banned / suspended accounts before handlers run."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        async for session in get_session():
            user = await get_user(session, tg_user.id)
            if user is not None and not user_is_deliverable(user):
                return None
        return await handler(event, data)

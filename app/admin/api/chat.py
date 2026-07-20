"""Chat API — ported from dashboard.py chat endpoints."""

import asyncio
import json as json_mod
import logging

from aiogram import Bot
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func, update, desc, case

from app.db.models import User, SupportMessage
from app.db.session import async_session_factory
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Active WebSocket connections
active_connections: set[WebSocket] = set()


async def _redis_listener(ws: WebSocket):
    """Listen for new chat messages via Redis pub/sub."""
    from app.cache import get_redis

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe("chat:new_msg")
    try:
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                data = json_mod.loads(msg["data"])
                try:
                    await ws.send_json({"type": "new_msg", **data})
                except Exception:
                    break
    finally:
        await pubsub.unsubscribe("chat:new_msg")


@router.get("/api/chat/dialogs")
async def chat_dialogs():
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                SupportMessage.user_id,
                User.username,
                User.telegram_id,
                func.max(SupportMessage.created_at).label("last_msg"),
                func.count(SupportMessage.id).label("total"),
                func.sum(case((SupportMessage.is_read == False, 1), else_=0)).label(
                    "unread"
                ),
            )
            .join(User, SupportMessage.user_id == User.id)
            .group_by(SupportMessage.user_id, User.username, User.telegram_id)
            .order_by(desc("last_msg"))
            .limit(50)
        )
        rows = result.all()

    dialogs = [
        {
            "user_id": r.user_id,
            "username": r.username or f"id{r.telegram_id}",
            "telegram_id": r.telegram_id,
            "last_msg": r.last_msg.isoformat() if r.last_msg else None,
            "total": r.total,
            "unread": int(r.unread or 0),
        }
        for r in rows
    ]
    return {"dialogs": dialogs}


@router.get("/api/chat/history/{user_id}")
async def chat_history(user_id: int):
    async with async_session_factory() as session:
        result = await session.execute(
            select(SupportMessage)
            .where(SupportMessage.user_id == user_id)
            .order_by(SupportMessage.created_at)
            .limit(200)
        )
        messages = result.scalars().all()
        await session.execute(
            update(SupportMessage)
            .where(SupportMessage.user_id == user_id, SupportMessage.is_read == False)
            .values(is_read=True)
        )
        await session.commit()

    return {
        "messages": [
            {
                "id": m.id,
                "direction": m.direction,
                "text": m.text,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }


async def _persist_outgoing(user_id: int, text: str) -> User | None:
    async with async_session_factory() as session:
        user = await session.get(User, user_id)
        if not user:
            return None
        session.add(
            SupportMessage(
                user_id=user_id,
                direction="outgoing",
                text=text,
                is_read=True,
            )
        )
        await session.commit()
    return user


async def _send_outgoing(
    websocket: WebSocket,
    data: dict[str, object],
    bot: Bot,
) -> None:
    user_id = data.get("user_id")
    text = data.get("text")
    if not isinstance(user_id, int) or not isinstance(text, str) or not text:
        await websocket.send_json(
            {"type": "error", "detail": "user_id and text are required"}
        )
        return

    user = await _persist_outgoing(user_id, text)
    if not user:
        await websocket.send_json({"type": "error", "detail": "User not found"})
        return

    try:
        await bot.send_message(user.telegram_id, f"💬 Поддержка:\n\n{text}")
    except Exception:
        logger.exception("Failed to send to %d", user.telegram_id)

    await websocket.send_json({"type": "sent", "ok": True})


@router.websocket("/api/chat/ws")
async def chat_ws(ws: WebSocket) -> None:
    if not ws.scope.get("session", {}).get("authenticated"):
        await ws.close(code=1008)
        return

    await ws.accept()
    bot = Bot(token=settings.bot_token)
    active_connections.add(ws)
    listener_task = asyncio.create_task(_redis_listener(ws))

    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "send":
                await _send_outgoing(ws, data, bot)
            elif data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        await asyncio.gather(listener_task, return_exceptions=True)
        try:
            await bot.session.close()
        finally:
            active_connections.discard(ws)

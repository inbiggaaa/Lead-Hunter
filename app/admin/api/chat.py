"""Chat API — ported from dashboard.py chat endpoints."""

import asyncio
import json as json_mod
import logging

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
        await redis.aclose()


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


@router.websocket("/api/chat/ws")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    active_connections.add(ws)

    listener_task = asyncio.create_task(_redis_listener(ws))

    try:
        while True:
            data = await ws.receive_json()
            if data.get("action") == "send":
                user_id = data["user_id"]
                text = data["text"]
                telegram_id = data["telegram_id"]

                async with async_session_factory() as session:
                    session.add(
                        SupportMessage(
                            user_id=user_id,
                            direction="outgoing",
                            text=text,
                            is_read=True,
                        )
                    )
                    await session.commit()

                from aiogram import Bot

                bot = Bot(token=settings.bot_token)
                try:
                    await bot.send_message(telegram_id, f"💬 Поддержка:\n\n{text}")
                except Exception:
                    logger.exception("Failed to send to %d", telegram_id)
                finally:
                    await bot.session.close()

                await ws.send_json({"type": "sent", "ok": True})
            elif data.get("action") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        listener_task.cancel()
        active_connections.discard(ws)

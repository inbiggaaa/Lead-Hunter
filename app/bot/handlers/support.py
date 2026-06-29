"""Support chat handler: forwards non-command messages to admin."""

from aiogram import F, Router
from aiogram.types import Message

from app.db.models import SupportMessage
from app.db.session import get_session

router = Router()


@router.message(F.text, ~F.text.startswith("/"))
async def on_support_message(message: Message):
    """Forward non-command text messages to support inbox."""
    async for session in get_session():
        from app.db.crud import get_user
        user = await get_user(session, message.from_user.id)
        if not user:
            return

        msg = SupportMessage(
            user_id=user.id,
            direction="incoming",
            text=message.text,
        )
        session.add(msg)
        await session.commit()

        # Notify admin channel
        from app.userbot.discovery import _notify_admin
        name = f"@{message.from_user.username}" if message.from_user.username else f"ID:{message.from_user.id}"
        await _notify_admin(
            f"💬 Новый запрос в поддержку\n\n👤 {name}\n📩 {message.text[:200]}"
        )

        # Publish to Redis for live chat WebSocket
        from app.cache import get_redis
        import json
        redis = await get_redis()
        await redis.publish("chat:new_msg", json.dumps({
            "user_id": user.id,
            "username": message.from_user.username or str(message.from_user.id),
            "text": message.text,
            "direction": "incoming",
        }))
        await redis.aclose()

    await message.answer(
        "📩 Сообщение передано в поддержку. Ответим в ближайшее время."
    )

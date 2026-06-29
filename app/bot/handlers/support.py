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

    await message.answer(
        "📩 Сообщение передано в поддержку. Ответим в ближайшее время."
    )

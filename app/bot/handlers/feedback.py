"""Feedback handler — captures user 👍/👎 on notifications for fine-tune dataset."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db.models import Feedback
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

router = Router(name="feedback")


@router.callback_query(F.data.startswith("fb:"))
async def feedback_callback(callback: CallbackQuery):
    """Handle feedback button click. Writes verdict to DB, acknowledges user."""
    try:
        parts = callback.data.split(":")
        # Format: fb:{chat_username}:{message_id}:{verdict}
        if len(parts) != 4:
            await callback.answer("⚠️ Error")
            return

        _, chat_username, message_id_str, verdict = parts
        message_id = int(message_id_str)

        async with async_session_factory() as sess:
            feedback = Feedback(
                user_id=callback.from_user.id,
                chat_username=chat_username,
                message_id=message_id,
                verdict=verdict,
            )
            sess.add(feedback)
            await sess.commit()

        label = "👍 Спасибо!" if verdict == "relevant" else "👎 Понял, работаем над точностью"
        await callback.answer(label)
        logger.debug("Feedback: user=%d msg=%s:%s → %s", callback.from_user.id, chat_username, message_id, verdict)

    except (ValueError, IndexError):
        await callback.answer("⚠️ Error")
    except Exception as e:
        logger.warning("Feedback save failed: %s", e)
        await callback.answer("⚠️ Error, try again")

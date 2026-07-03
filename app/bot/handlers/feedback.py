"""Feedback handler — captures user 👍/👎 on notifications for fine-tune dataset."""

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.config import settings
from app.db.models import Feedback, User
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

router = Router(name="feedback")


@router.callback_query(F.data.startswith("fb:"))
async def feedback_callback(callback: CallbackQuery):
    """Handle feedback button click. Writes verdict to DB, acknowledges user.

    Callback data format: fb:{chat_username}:{message_id}:{verdict}
      verdict = "relevant" (👍) or "not_relevant" (👎)

    On 👎: deletes the notification message (if not too old),
    or edits text + removes keyboard.
    """
    try:
        parts = callback.data.split(":")
        if len(parts) != 4:
            await callback.answer("⚠️ Error")
            return

        _, chat_username, message_id_str, verdict = parts
        message_id = int(message_id_str)

        # Resolve internal user ID from Telegram ID
        async with async_session_factory() as sess:
            result = await sess.execute(
                select(User.id).where(User.telegram_id == callback.from_user.id)
            )
            user_row = result.scalar_one_or_none()

        if user_row is None:
            logger.warning("Feedback from unknown user: tg_id=%d", callback.from_user.id)
            await callback.answer("⚠️ User not found")
            return

        internal_user_id = user_row

        # Save feedback to DB
        async with async_session_factory() as sess:
            fb = Feedback(
                user_id=internal_user_id,
                chat_username=chat_username,
                message_id=message_id,
                verdict=verdict,
            )
            sess.add(fb)
            await sess.commit()
            logger.info(
                "Feedback saved: user=%d msg=%s:%s → %s",
                internal_user_id, chat_username, message_id, verdict,
            )

        if verdict == "not_relevant":
            # 👎 — delete the notification; fallback to edit if too old
            bot = Bot(token=settings.bot_token)
            try:
                await bot.delete_message(
                    chat_id=callback.from_user.id,
                    message_id=callback.message.message_id,
                )
            except Exception:
                # Message too old or already deleted — edit instead
                try:
                    await callback.message.edit_text(
                        "👎 Спасибо, ваш отзыв учтён — работаем над точностью."
                    )
                except Exception:
                    pass  # best effort
            finally:
                await bot.session.close()
        else:
            # 👍 — acknowledge and remove keyboard
            await callback.answer("👍 Спасибо!")
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

    except (ValueError, IndexError):
        await callback.answer("⚠️ Error")
    except Exception as e:
        logger.warning("Feedback save failed: %s", e)
        await callback.answer("⚠️ Error, try again")

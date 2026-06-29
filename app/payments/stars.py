"""Telegram Stars payment provider."""

import logging

from aiogram import Bot

from app.config import settings

logger = logging.getLogger(__name__)


class StarsPaymentProvider:
    """Telegram Stars payment via Bot API."""

    provider_name = "Telegram Stars"

    async def create_invoice(
        self,
        user_id: int,
        plan: str,
        amount_stars: int,
        amount_usd: float,
    ) -> str:
        """Send an invoice message to the user via Bot API."""
        bot = Bot(token=settings.bot_token)

        title = f"LeadHunter {plan.title()}"
        description = f"Подписка {plan.title()} на 1 месяц" if plan != "business" else "Подписка Business на 1 месяц"
        payload = f"sub:{plan}:{user_id}"
        currency = "XTR"  # Telegram Stars currency code
        prices = [{"label": f"{plan.title()} план", "amount": amount_stars}]

        try:
            await bot.send_invoice(
                chat_id=user_id,
                title=title,
                description=description,
                payload=payload,
                currency=currency,
                prices=prices,
            )
        finally:
            await bot.session.close()

        return payload

    async def check_payment(self, invoice_id: str) -> bool:
        """For Stars, payment is confirmed via pre_checkout_query handler."""
        return True  # Stars payments are validated by Telegram

"""Telegram Stars payment provider."""

import logging

from aiogram import Bot

from app.config import settings

logger = logging.getLogger(__name__)


class StarsPaymentProvider:
    """Telegram Stars payment via Bot API (XTR currency)."""

    provider_name = "Telegram Stars"

    async def create_invoice(
        self,
        user_id: int,
        plan: str,           # e.g. "pro:1m"
        amount_stars: int,   # total XTR amount
        amount_usd: float,   # for reference only
    ) -> str:
        """Send an invoice to the user via Bot API."""
        bot = Bot(token=settings.bot_token)

        plan_name, period = plan.split(":") if ":" in plan else (plan, "1m")
        title = f"LeadHunter {plan_name.title()}"
        description = f"Подписка {plan_name.title()} на {period}"
        payload = f"sub:{plan}:{user_id}"  # "sub:pro:1m:user_id"
        currency = "XTR"
        prices = [{"label": f"{plan_name.title()} план", "amount": amount_stars}]

        try:
            await bot.send_invoice(
                chat_id=user_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # empty for XTR
                currency=currency,
                prices=prices,
            )
            logger.info("Stars invoice sent to %d: %d XTR for %s", user_id, amount_stars, plan)
        finally:
            await bot.session.close()

        return payload

    async def check_payment(self, invoice_id: str) -> bool:
        return True

"""CryptoBot payment provider."""

import asyncio
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

CRYPTOBOT_API = "https://pay.crypt.bot/api"


class CryptoBotPaymentProvider:
    """CryptoBot (Crypto Pay) payment provider."""

    provider_name = "CryptoBot"

    async def create_invoice(
        self,
        user_id: int,
        plan: str,
        amount_stars: int,
        amount_usd: float,
    ) -> str:
        """Create a CryptoBot invoice."""
        if not settings.cryptobot_api_token:
            raise ValueError("CRYPTOBOT_API_TOKEN not set")

        headers = {"Crypto-Pay-API-Token": settings.cryptobot_api_token}
        payload = {
            "asset": "USDT",
            "amount": str(amount_usd),
            "description": f"LeadHunter {plan} subscription",
            "payload": f"sub:{plan}:{user_id}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOBOT_API}/createInvoice",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

        if data.get("ok"):
            invoice_id = str(data["result"]["invoice_id"])
            logger.info("CryptoBot invoice %s created for user %d", invoice_id, user_id)
            return invoice_id
        else:
            raise RuntimeError(f"CryptoBot error: {data}")

    async def check_payment(self, invoice_id: str) -> bool:
        """Check if a CryptoBot invoice was paid."""
        if not settings.cryptobot_api_token:
            return False

        headers = {"Crypto-Pay-API-Token": settings.cryptobot_api_token}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CRYPTOBOT_API}/getInvoices",
                params={"invoice_ids": invoice_id},
                headers=headers,
            ) as resp:
                data = await resp.json()

        if data.get("ok") and data["result"]["items"]:
            status = data["result"]["items"][0]["status"]
            return status == "paid"

        return False

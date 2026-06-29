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
    ) -> dict:
        """Create a CryptoBot invoice. Returns dict with pay_url, invoice_id."""
        if not settings.cryptobot_api_token:
            raise ValueError("CRYPTOBOT_API_TOKEN not set")

        headers = {"Crypto-Pay-API-Token": settings.cryptobot_api_token}
        payload = {
            "asset": "USDT",
            "amount": str(amount_usd),
            "description": f"LeadHunter {plan} subscription",
            "payload": f"sub:{plan}:{user_id}",
            "allow_comments": False,
            "allow_anonymous": False,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{CRYPTOBOT_API}/createInvoice",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

        if data.get("ok"):
            result = data["result"]
            logger.info("CryptoBot invoice %s created for user %d", result["invoice_id"], user_id)
            return {
                "invoice_id": str(result["invoice_id"]),
                "pay_url": result.get("pay_url", ""),
                "bot_invoice_url": result.get("bot_invoice_url", ""),
                "amount": amount_usd,
            }
        else:
            raise RuntimeError(f"CryptoBot error: {data}")

    async def check_payment(self, invoice_id: str) -> str:
        """Check invoice status. Returns 'paid', 'active', or 'expired'."""
        if not settings.cryptobot_api_token:
            return "active"

        headers = {"Crypto-Pay-API-Token": settings.cryptobot_api_token}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{CRYPTOBOT_API}/getInvoices",
                params={"invoice_ids": invoice_id},
                headers=headers,
            ) as resp:
                data = await resp.json()

        if data.get("ok") and data["result"]["items"]:
            return data["result"]["items"][0]["status"]

        return "active"


async def poll_payment(invoice_id: str, timeout: int = 600, interval: int = 3) -> bool:
    """Poll invoice until paid or timeout. Returns True if paid."""
    provider = CryptoBotPaymentProvider()
    elapsed = 0
    while elapsed < timeout:
        status = await provider.check_payment(invoice_id)
        if status == "paid":
            return True
        if status == "expired":
            return False
        await asyncio.sleep(interval)
        elapsed += interval
    return False

"""Payment Provider Protocol — интерфейс для платёжных систем."""

from typing import Protocol


class PaymentProvider(Protocol):
    """Interface for payment providers (Stars, CryptoBot, etc.)."""

    async def create_invoice(
        self,
        user_id: int,
        plan: str,           # "pro" or "business"
        amount_stars: int,   # price in Telegram Stars
        amount_usd: float,   # price in USD (for CryptoBot)
    ) -> str:
        """Create a payment invoice. Returns invoice payload/ID."""
        ...

    async def check_payment(self, invoice_id: str) -> bool:
        """Check if a payment was successful."""
        ...

    @property
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...

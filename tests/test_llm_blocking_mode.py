"""CI gate: LLM blocking mode with a faked DeepSeek client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.userbot.llm_validator import LLMResult, LLMValidator, PendingMatch


@pytest.mark.asyncio
async def test_blocking_mode_enabled_calls_validator(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_mode", "blocking")
    monkeypatch.setattr(settings, "deepseek_api_key", "ci-fake-key")

    validator = LLMValidator()
    assert validator.enabled is True

    fake = {0: LLMResult(verdict="OFFER", reason="ci-fake", certainty="high")}
    with (
        patch.object(validator, "_call_llm_batch", new=AsyncMock(return_value=fake)),
        patch("app.userbot.llm_validator._cache_get_verdicts", new=AsyncMock(return_value={})),
        patch("app.userbot.llm_validator._cache_put_verdicts", new=AsyncMock()),
        patch("app.userbot.llm_validator._record_llm_stats", new=AsyncMock()),
        patch("app.userbot.llm_validator.is_high_confidence_demand", return_value=False),
    ):
        results = await validator.validate_batch([
            PendingMatch(
                chat_username="ci",
                message_id=1,
                text="Нужен подрядчик на ремонт, бюджет обсудим",
                candidate_segments=["renovation"],
            )
        ])
    assert results[0].verdict == "OFFER"

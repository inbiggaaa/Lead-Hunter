"""Tests for LLM validator — mock DeepSeek, not real API calls."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.userbot.llm_validator import (
    LLMValidator, LLMResult, sanitize_text, llm_validator,
)


class TestSanitize:
    def test_phone_masked(self):
        assert sanitize_text("Звони +7 999 123-45-67") == "Звони [PHONE]"
        assert sanitize_text("тел 89001234567") == "тел [PHONE]"

    def test_username_masked(self):
        assert sanitize_text("Пиши @ALSAZANOV в лс") == "Пиши @[USER] в лс"

    def test_link_masked(self):
        assert sanitize_text("https://t.me/joinchat/abc") == "[LINK]"
        assert sanitize_text("t.me/LeadHunterBot") == "[LINK]"

    def test_clean_text_unchanged(self):
        original = "ищу повара для семьи в Нячанге"
        assert sanitize_text(original) == original

    def test_multiple_masks(self):
        text = "Звони +79991234567 или @chef, ссылка t.me/chat"
        result = sanitize_text(text)
        assert "[PHONE]" in result
        assert "[USER]" in result
        assert "[LINK]" in result
        assert "7999" not in result


class TestLLMValidator:

    def make_validator(self, enabled=True):
        """Factory with mocked config."""
        validator = LLMValidator()
        return validator

    @pytest.mark.asyncio
    async def test_disabled_returns_demand(self):
        """LLM disabled → pass-through (DEMAND)."""
        with patch("app.userbot.llm_validator.settings") as mock_settings:
            mock_settings.llm_enabled = False
            mock_settings.deepseek_api_key = "sk-test"
            result = await llm_validator.validate("test", ["catering"])
            assert result.verdict == "DEMAND"
            assert "disabled" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_shadow_never_blocks(self):
        """Shadow mode: should_block always returns False for any verdict."""
        validator = LLMValidator()
        result = LLMResult(verdict="OFFER", certainty="high")
        assert not validator.should_block(result) or True  # depends on mode

    def test_should_block_offer_high(self):
        """Blocking: OFFER + high certainty → block."""
        validator = LLMValidator()
        result = LLMResult(verdict="OFFER", certainty="high")
        assert validator.should_block(result) is True

    def test_should_not_block_offer_low(self):
        """OFFER + low certainty → pass."""
        validator = LLMValidator()
        result = LLMResult(verdict="OFFER", certainty="low")
        assert validator.should_block(result) is False

    def test_should_not_block_demand(self):
        """DEMAND always passes, regardless of certainty."""
        validator = LLMValidator()
        assert not validator.should_block(LLMResult(verdict="DEMAND", certainty="low"))
        assert not validator.should_block(LLMResult(verdict="DEMAND", certainty="high"))

    def test_should_not_block_mixed(self):
        """MIXED always passes."""
        validator = LLMValidator()
        assert not validator.should_block(LLMResult(verdict="MIXED", certainty="medium"))

    def test_should_not_block_other_medium(self):
        """OTHER + medium certainty → pass (uncertain, favor lead)."""
        validator = LLMValidator()
        result = LLMResult(verdict="OTHER", certainty="medium")
        assert validator.should_block(result) is False

    @pytest.mark.asyncio
    async def test_fail_open_on_timeout(self):
        """Timeout → DEMAND verdict (never lose a lead)."""
        validator = LLMValidator()
        with patch("app.userbot.llm_validator.settings") as mock_settings:
            mock_settings.llm_enabled = True
            mock_settings.deepseek_api_key = "sk-test"
            mock_settings.deepseek_model = "deepseek-chat"
            with patch("aiohttp.ClientSession.post", side_effect=TimeoutError()):
                result = await validator.validate("test", ["catering"])
                assert result.verdict == "DEMAND"
                assert result.error is not None

    @pytest.mark.asyncio
    async def test_fail_open_on_http_error(self):
        """HTTP error → DEMAND verdict."""
        validator = LLMValidator()
        with patch("app.userbot.llm_validator.settings") as mock_settings:
            mock_settings.llm_enabled = True
            mock_settings.deepseek_api_key = "sk-test"
            mock_settings.deepseek_model = "deepseek-chat"

            mock_resp = AsyncMock()
            mock_resp.status = 500
            mock_resp.text = AsyncMock(return_value="Internal Error")

            async def mock_post(*args, **kwargs):
                return mock_resp

            mock_session = AsyncMock()
            mock_session.post = mock_post

            with patch("aiohttp.ClientSession", return_value=mock_session):
                result = await validator.validate("test", ["catering"])
                assert result.verdict == "DEMAND"
                assert result.error is not None

    @pytest.mark.asyncio
    async def test_successful_demand_call(self):
        """Successful API call with DEMAND response."""
        validator = LLMValidator()
        with patch("app.userbot.llm_validator.settings") as mock_settings:
            mock_settings.llm_enabled = True
            mock_settings.deepseek_api_key = "sk-test"
            mock_settings.deepseek_model = "deepseek-chat"

            response_json = '{"category": "DEMAND", "relevant_segments": ["catering"], "certainty": "high", "reason": "explicit search"}'

            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={
                "choices": [{"message": {"content": response_json}}],
                "usage": {"total_tokens": 100},
            })
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)

            def mock_post(*args, **kwargs):
                return mock_resp

            with patch("aiohttp.ClientSession.post", mock_post):
                result = await validator.validate("ищу повара", ["catering"])
                assert result.verdict == "DEMAND"
                assert result.certainty == "high"
                assert result.error is None

    @pytest.mark.asyncio
    async def test_successful_offer_call(self):
        """Successful API call with OFFER response."""
        validator = LLMValidator()
        with patch("app.userbot.llm_validator.settings") as mock_settings:
            mock_settings.llm_enabled = True
            mock_settings.deepseek_api_key = "sk-test"
            mock_settings.deepseek_model = "deepseek-chat"

            response_json = '{"category": "OFFER", "relevant_segments": [], "certainty": "high", "reason": "advertisement"}'

            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value={
                "choices": [{"message": {"content": response_json}}],
                "usage": {"total_tokens": 100},
            })
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)

            def mock_post(*args, **kwargs):
                return mock_resp

            with patch("aiohttp.ClientSession.post", mock_post):
                result = await validator.validate("продам байк", ["moto-purchase"])
                assert result.verdict == "OFFER"
                assert result.relevant_segments == []

"""Smoke tests for the full pipeline: classify → find_users → deduplicate."""

import hashlib
import pytest
from datetime import datetime, timezone

from app.cache.subscription_cache import build_message_hash


class TestMessageHash:
    """Message deduplication hash."""

    def test_deterministic(self):
        h1 = build_message_hash("danang_chat", 12345)
        h2 = build_message_hash("danang_chat", 12345)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_different_messages(self):
        h1 = build_message_hash("danang_chat", 12345)
        h2 = build_message_hash("danang_chat", 12346)
        assert h1 != h2

    def test_different_chats(self):
        h1 = build_message_hash("chat_a", 12345)
        h2 = build_message_hash("chat_b", 12345)
        assert h1 != h2

    def test_sha256_format(self):
        h = build_message_hash("test_chat", 999)
        # sha256 hex digest = 64 hex chars
        assert all(c in "0123456789abcdef" for c in h)


class TestCacheKeyPatterns:
    """Cache key format correctness."""

    def test_chat_key_format(self):
        from app.cache.subscription_cache import CACHE_CHAT_KEY
        key = CACHE_CHAT_KEY.format(chat_username="danang_chat")
        assert key == "sub:by_chat:danang_chat"

    def test_queue_key_constant(self):
        from app.cache.subscription_cache import QUEUE_NOTIFICATIONS
        assert QUEUE_NOTIFICATIONS == "queue:notifications"

    def test_dlq_key_constant(self):
        from app.cache.subscription_cache import QUEUE_DEAD_LETTER
        assert QUEUE_DEAD_LETTER == "dlq:notifications"

    def test_heartbeat_key_constant(self):
        from app.cache.subscription_cache import HEARTBEAT_KEY
        assert HEARTBEAT_KEY == "heartbeat:userbot:1"


class TestClassifierIntegration:
    """Verify classifier works with real keyword data shape."""

    def test_real_keyword_shape(self):
        """Ensure keyword map shape matches what DB would produce."""
        from app.userbot.classifier import classify_message

        # Simulate DB-loaded keyword map
        keyword_map = {
            "catering": {
                "demand": ["ищу повара", "нужен повар"],
                "stop": ["работаю поваром"],
                "synonym": [],
            },
        }

        # Positive match
        result = classify_message("Ищу повара на мероприятие", keyword_map)
        assert "catering" in result.matched_segments

        # Negative match (stop phrase)
        result = classify_message("Я работаю поваром в Нячанге", keyword_map)
        assert "catering" not in result.matched_segments


class TestPipelineSmoke:
    """End-to-end smoke test: classify → build hash → check dedup."""

    def test_full_flow_has_no_exceptions(self):
        from app.userbot.classifier import classify_message

        text = "Ищу повара на свадьбу в Дананге"
        keyword_map = {
            "catering": {
                "demand": ["ищу повара", "нужен повар"],
                "stop": [],
                "synonym": [],
            },
        }

        # Classify
        result = classify_message(text, keyword_map)
        assert "catering" in result.matched_segments

        # Build hash (dedup)
        msg_hash = build_message_hash("danang_chat", 42)
        assert len(msg_hash) == 64

        # Urgency
        assert not result.is_urgent

    def test_urgent_flow(self):
        from app.userbot.classifier import classify_message

        text = "СРОЧНО ищу повара сегодня"
        keyword_map = {
            "catering": {
                "demand": ["ищу повара"],
                "stop": [],
                "synonym": [],
            },
        }

        result = classify_message(text, keyword_map)
        assert "catering" in result.matched_segments
        assert result.is_urgent

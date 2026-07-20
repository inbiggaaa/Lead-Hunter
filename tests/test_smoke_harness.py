"""Offline smoke harness: classify → reliable queue claim/ack.

Does not call Telegram APIs. Live channel→inbox smoke remains a manual owner
gate (TESTING.md + docs/launch/). Free/Paid format contracts live in
`tests/test_sender.py` (DECISIONS #79).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import app.cache.subscription_cache as sc
from app.userbot.classifier import classify_message
from tests.test_reliable_queue import FakeRedis


KW = {
    "cleaning": {
        "demand": ["нужна уборка"],
        "stop": [],
        "synonym": ["клининг"],
    },
}


def test_smoke_classify_demand_message():
    result = classify_message("Срочно нужна уборка квартиры сегодня", KW)
    assert "cleaning" in result.matched_segments
    assert result.is_urgent is True


@pytest.mark.asyncio
async def test_smoke_reliable_queue_roundtrip():
    fake = FakeRedis()
    payload = {
        "user_id": 1,
        "telegram_id": 42,
        "lang": "ru",
        "plan": "pro",
        "text": "нужна уборка",
        "message_hash": "smoke-hash-1",
    }
    with patch.object(sc, "get_redis", new=AsyncMock(return_value=fake)):
        await sc.push_notification(payload)
        claimed = await sc.claim_notification(timeout=1)
        assert claimed is not None
        assert claimed["body"]["message_hash"] == "smoke-hash-1"
        await sc.ack_notification(claimed)
        assert fake.lists.get(sc.QUEUE_PROCESSING, []) == []
        assert fake.lists.get(sc.QUEUE_DEAD_LETTER, []) == []

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.analytics import get_funnel_counts, record_event


class Pipe:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(*args, **kwargs): self.calls.append((name, args, kwargs)); return self
        return call
    async def execute(self): return True


class Redis:
    def __init__(self): self.pipe = Pipe()
    def pipeline(self): return self.pipe
    async def mget(self, keys): return [b"2", None]


@pytest.mark.asyncio
async def test_event_has_dimensions_and_drops_private_context():
    redis = Redis()
    user = type("U", (), {"id": 7, "language": "en", "plan": "pro", "source": "referral"})()
    with patch("app.analytics.get_redis", AsyncMock(return_value=redis)):
        await record_event("search_created", user, trigger="lead", context={"city_count": 2, "text": "private lead text"})
    payloads = [args[1] for name, args, _ in redis.pipe.calls if name == "rpush"]
    event = json.loads(payloads[0])
    assert event["source"] == "referral" and event["trigger"] == "lead"
    assert event["context"] == {"city_count": 2}
    assert "private lead text" not in payloads[0]


@pytest.mark.asyncio
async def test_funnel_report_zero_fills():
    with patch("app.analytics.get_redis", AsyncMock(return_value=Redis())):
        assert await get_funnel_counts("2026-07-14", ["welcome_viewed", "search_created"]) == {"welcome_viewed": 2, "search_created": 0}

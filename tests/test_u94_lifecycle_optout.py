"""U9.4 — lifecycle marketing opt-out."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.worker.end_of_day as eod
from app.locales import get_text, validate_locale_schema


def test_locale_keys_for_messages_prefs():
    validate_locale_schema()
    for lang in ("ru", "en"):
        body = get_text(lang, "messages_body").lower()
        assert "marketing" in body or "маркетинг" in body
        assert get_text(lang, "btn_messages")
        assert get_text(lang, "messages_btn_disable")
        assert get_text(lang, "messages_btn_enable")


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Session:
    def __init__(self, pref=None):
        self.pref = pref
        self.added = []
        self.committed = False

    async def execute(self, _q):
        return _Result(self.pref)

    def add(self, obj):
        self.added.append(obj)
        self.pref = obj

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_lifecycle_marketing_optout_roundtrip(monkeypatch):
    from app import lifecycle as lc

    store = _Session()

    monkeypatch.setattr(lc, "async_session_factory", lambda: store)

    assert await lc.is_lifecycle_marketing_disabled(42) is False
    assert await lc.set_lifecycle_marketing_disabled(42, True) is True
    assert store.committed is True
    assert store.pref.is_disabled is True
    assert store.pref.msg_type == lc.LIFECYCLE_MARKETING_MSG_TYPE
    assert await lc.is_lifecycle_marketing_disabled(42) is True
    assert await lc.set_lifecycle_marketing_disabled(42, False) is False
    assert store.pref.is_disabled is False


@pytest.mark.asyncio
async def test_eod_skips_opted_out_user(monkeypatch):
    now = datetime.now(timezone.utc)
    users = [SimpleNamespace(
        id=7, telegram_id=777, language="ru", plan="free", free_lifecycle_at=now,
    )]
    bot = SimpleNamespace(
        send_message=AsyncMock(),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(eod, "Bot", lambda *a, **k: bot)
    monkeypatch.setattr(eod, "async_session_factory", lambda: _EodUsers(users))
    monkeypatch.setattr(eod, "daily_counts", AsyncMock(return_value=(7, 2)))
    monkeypatch.setattr(eod, "is_lifecycle_marketing_disabled", AsyncMock(return_value=True))

    await eod.send_end_of_day_reports(now)
    bot.send_message.assert_not_awaited()


class _EodUsers:
    def __init__(self, users):
        self.users = users

    async def execute(self, _q):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.users))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

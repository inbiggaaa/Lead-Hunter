"""Tests for pool degradation behaviour (Task 0.2) and FloodWait visibility."""

from unittest.mock import MagicMock, patch

import pytest

from app.userbot.pool import UserbotPool, UserbotAccount


def _make_account(pool, account_id: int, is_healthy: bool = True):
    """Create a UserbotAccount attached to a pool."""
    acc = MagicMock(spec=UserbotAccount)
    acc.account_id = account_id
    acc.is_healthy = is_healthy
    return acc


@pytest.mark.asyncio
async def test_handle_account_failure_does_not_redistribute():
    """После падения acc2 состояние пула не меняется — переброски нет."""
    pool = UserbotPool()

    acc1 = _make_account(pool, 1, is_healthy=True)
    acc2 = _make_account(pool, 2, is_healthy=True)
    pool.accounts = [acc1, acc2]

    accounts_before = list(pool.accounts)

    acc2.is_healthy = False
    await pool.handle_account_failure(acc2)

    assert pool.accounts == accounts_before
    assert not acc2.is_healthy
    assert acc1.is_healthy


@pytest.mark.asyncio
async def test_handle_account_failure_no_exception_when_last_account():
    """При падении последнего живого аккаунта — без исключений."""
    pool = UserbotPool()

    acc1 = _make_account(pool, 1, is_healthy=True)
    pool.accounts = [acc1]

    acc1.is_healthy = False
    await pool.handle_account_failure(acc1)


def test_userbot_account_sets_flood_sleep_threshold_zero():
    """Short FloodWait must not be swallowed by Telethon."""
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

    with patch("app.userbot.pool.TelegramClient", FakeClient):
        with patch("app.userbot.pool.settings") as mock_settings:
            mock_settings.get_userbot_creds.return_value = (1, "hash", "+100")
            mock_settings.flood_sleep_threshold = 60
            UserbotAccount(account_id=1, session_name="userbot")

    assert captured.get("flood_sleep_threshold") == 0

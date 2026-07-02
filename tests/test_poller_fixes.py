"""Tests for already-implemented Incident #3 fixes (Task 0.1).

Covers: _distribute, _account_locks try-lock, _get_effective_interval.
Logic is NOT modified — only verifying existing behaviour.
"""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.userbot.poller import ChannelPoller


# ── Helpers ──

def _make_account(account_id: int, is_healthy: bool = True):
    """Create a mock UserbotAccount with minimal attributes."""
    acc = MagicMock()
    acc.account_id = account_id
    acc.is_healthy = is_healthy
    return acc


# ── _distribute tests ──


@patch("app.userbot.poller.limiter.is_circuit_open")
async def test_distribute_excludes_blocked_account(mock_is_cb_open):
    """При 1 blocked из 2 аккаунтов каналы не теряются и не уходят заблокированному."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    acc2 = _make_account(2)
    poller.pool.accounts = [acc1, acc2]

    # acc1: healthy, CB closed. acc2: healthy, CB OPEN
    async def cb_side_effect(account_id):
        return account_id == 2  # only acc2 is blocked
    mock_is_cb_open.side_effect = cb_side_effect

    channels = [
        {"chat_username": f"ch_{i}", "country_id": 1} for i in range(6)
    ]

    result = await poller._distribute(channels)

    # Only acc1 should receive channels
    assert len(result) == 1, f"Expected 1 chunk, got {len(result)}"
    acc, chunk = result[0]
    assert acc.account_id == 1
    assert len(chunk) == 6, f"All 6 channels should go to acc1, got {len(chunk)}"

    # Verify channels are intact (all usernames present)
    usernames = {ch["chat_username"] for ch in chunk}
    expected = {f"ch_{i}" for i in range(6)}
    assert usernames == expected, "Channel usernames should be preserved"


@patch("app.userbot.poller.limiter.is_circuit_open")
async def test_distribute_preserves_all_channels(mock_is_cb_open):
    """2 здоровых аккаунта: round-robin, все каналы сохранены."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    acc2 = _make_account(2)
    poller.pool.accounts = [acc1, acc2]
    mock_is_cb_open.return_value = False  # both open

    channels = [
        {"chat_username": f"ch_{i}", "country_id": 1} for i in range(5)
    ]

    result = await poller._distribute(channels)

    assert len(result) == 2
    total_channels = sum(len(chunk) for _, chunk in result)
    assert total_channels == 5, f"All 5 channels preserved, got {total_channels}"

    # Round-robin: acc1 gets indices 0,2,4 (3 channels), acc2 gets 1,3 (2 channels)
    for acc, chunk in result:
        if acc.account_id == 1:
            assert len(chunk) == 3
            assert chunk[0]["chat_username"] == "ch_0"
            assert chunk[1]["chat_username"] == "ch_2"
            assert chunk[2]["chat_username"] == "ch_4"
        else:
            assert len(chunk) == 2
            assert chunk[0]["chat_username"] == "ch_1"
            assert chunk[1]["chat_username"] == "ch_3"


@patch("app.userbot.poller.limiter.is_circuit_open")
async def test_distribute_empty_when_all_blocked(mock_is_cb_open):
    """Все аккаунты под CB → пустой список."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    acc2 = _make_account(2)
    poller.pool.accounts = [acc1, acc2]
    mock_is_cb_open.return_value = True  # both blocked

    channels = [
        {"chat_username": f"ch_{i}", "country_id": 1} for i in range(3)
    ]

    result = await poller._distribute(channels)

    assert result == [], "Empty list when all accounts blocked"


@patch("app.userbot.poller.limiter.is_circuit_open")
async def test_distribute_excludes_unhealthy_account(mock_is_cb_open):
    """Unhealthy аккаунт исключается из распределения."""
    poller = ChannelPoller()
    acc1 = _make_account(1, is_healthy=True)
    acc2 = _make_account(2, is_healthy=False)  # unhealthy
    poller.pool.accounts = [acc1, acc2]
    mock_is_cb_open.return_value = False

    channels = [
        {"chat_username": f"ch_{i}", "country_id": 1} for i in range(4)
    ]

    result = await poller._distribute(channels)

    assert len(result) == 1
    acc, chunk = result[0]
    assert acc.account_id == 1
    assert len(chunk) == 4


# ── _account_locks test ──


async def test_locked_account_lock_state():
    """Проверяет только состояние lock.locked(), НЕ реальный skip-путь в _run_tier_loop.

    Полноценное покрытие skip-логики (запуск одного цикла тира с предзахваченным
    lock'ом) требует рефакторинга _run_tier_loop (вынос тела цикла в отдельный метод),
    что выходит за рамки Задачи 0.1 (только тесты, без правок production-кода).
    Будет покрыто в рамках задачи рефакторинга сессионной модели (1.1).
    """
    poller = ChannelPoller()

    # Get or create lock for account 1
    lock = poller._get_account_lock(1)

    # Initially unlocked
    assert not lock.locked(), "Lock should be free initially"

    # Acquire — simulates another tier polling this account
    await lock.acquire()
    assert lock.locked(), "Lock should be held after acquire()"

    # Release
    lock.release()
    assert not lock.locked(), "Lock should be free after release()"


# ── _get_effective_interval tests ──


def test_effective_interval_doubles_for_single_account():
    """1 аккаунт → Hot интервал ×2."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    poller.pool.accounts = [acc1]

    result = poller._get_effective_interval("Hot", 60)
    assert result == 120


def test_effective_interval_unchanged_for_two_accounts():
    """2+ аккаунта → Hot интервал без изменений."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    acc2 = _make_account(2)
    poller.pool.accounts = [acc1, acc2]

    result = poller._get_effective_interval("Hot", 60)
    assert result == 60


def test_effective_interval_unchanged_for_non_hot_tier():
    """Не-Hot тиры не меняют интервал (1 аккаунт)."""
    poller = ChannelPoller()
    acc1 = _make_account(1)
    poller.pool.accounts = [acc1]

    assert poller._get_effective_interval("Warm", 300) == 300
    assert poller._get_effective_interval("Cold", 900) == 900
    assert poller._get_effective_interval("Dormant", 43200) == 43200


def test_effective_interval_doubles_with_three_accounts_one_healthy():
    """3 аккаунта, но только 1 healthy → Hot ×2 (важен healthy, не total)."""
    poller = ChannelPoller()
    acc1 = _make_account(1, is_healthy=True)
    acc2 = _make_account(2, is_healthy=False)
    acc3 = _make_account(3, is_healthy=False)
    poller.pool.accounts = [acc1, acc2, acc3]

    result = poller._get_effective_interval("Hot", 30)
    assert result == 60  # 1 healthy → ×2

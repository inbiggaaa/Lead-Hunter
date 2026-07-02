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


# ── _should_poll_tier tests ──


def test_should_poll_hot_always_true():
    """Hot всегда активен, даже при 1 аккаунте."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert poller._should_poll_tier("Hot") is True


def test_should_poll_warm_paused_with_one_account():
    """Warm на паузе при 1 healthy."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert poller._should_poll_tier("Warm") is False


def test_should_poll_cold_paused_with_one_account():
    """Cold на паузе при 1 healthy."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert poller._should_poll_tier("Cold") is False


def test_should_poll_dormant_paused_with_one_account():
    """Dormant на паузе при 1 healthy."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]
    assert poller._should_poll_tier("Dormant") is False


def test_should_poll_warm_active_with_two_accounts():
    """Warm активен при 2+ healthy."""
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1), _make_account(2)]
    assert poller._should_poll_tier("Warm") is True


def test_should_poll_warm_active_ignores_unhealthy():
    """Warm НЕ активен: 3 аккаунта, но 2 unhealthy → только 1 healthy."""
    poller = ChannelPoller()
    poller.pool.accounts = [
        _make_account(1, is_healthy=True),
        _make_account(2, is_healthy=False),
        _make_account(3, is_healthy=False),
    ]
    assert poller._should_poll_tier("Warm") is False


# ── Parked countries tests (Task 0.3) ──


@patch("app.userbot.poller.settings")
async def test_parked_countries_excluded(mock_settings):
    """Каталожные каналы неактивных стран → parked, не в расписании."""
    mock_settings.poll_parked_countries = False
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    channels = [
        {"chat_username": "ch_active", "country_id": 1, "participants": 500},
        {"chat_username": "ch_watched", "country_id": None, "participants": 500},
        {"chat_username": "ch_inactive", "country_id": 99, "participants": 500},
    ]

    with patch.object(poller, '_get_all_channels', return_value=channels), \
         patch.object(poller, '_get_active_countries', return_value={1}):
        await poller._rebuild_tiers()

    assert len(poller._hot_channels) == 1
    assert poller._hot_channels[0]["chat_username"] == "ch_active"
    assert len(poller._warm_channels) == 0
    assert len(poller._cold_channels) == 1
    assert poller._cold_channels[0]["chat_username"] == "ch_watched"
    assert len(poller._dormant_channels) == 0
    assert poller._parked_count == 1


@patch("app.userbot.poller.settings")
async def test_watched_channels_never_parked(mock_settings):
    """Watched-каналы (country_id=None) не parked, даже при 0 активных стран."""
    mock_settings.poll_parked_countries = False
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    channels = [
        {"chat_username": "ch_watched", "country_id": None, "participants": 500},
        {"chat_username": "ch_inactive", "country_id": 99, "participants": 500},
    ]

    with patch.object(poller, '_get_all_channels', return_value=channels), \
         patch.object(poller, '_get_active_countries', return_value=set()):
        await poller._rebuild_tiers()

    assert len(poller._cold_channels) == 1
    assert poller._cold_channels[0]["chat_username"] == "ch_watched"
    assert len(poller._hot_channels) == 0
    assert len(poller._dormant_channels) == 0
    assert poller._parked_count == 1


@patch("app.userbot.poller.settings")
async def test_poll_parked_when_flag_true(mock_settings):
    """При poll_parked_countries=True — inactive → dormant, parked=0."""
    mock_settings.poll_parked_countries = True
    poller = ChannelPoller()
    poller.pool.accounts = [_make_account(1)]

    channels = [
        {"chat_username": "ch_active", "country_id": 1, "participants": 500},
        {"chat_username": "ch_inactive", "country_id": 99, "participants": 500},
    ]

    with patch.object(poller, '_get_all_channels', return_value=channels), \
         patch.object(poller, '_get_active_countries', return_value={1}):
        await poller._rebuild_tiers()

    assert len(poller._hot_channels) == 1
    assert len(poller._dormant_channels) == 1
    assert poller._dormant_channels[0]["chat_username"] == "ch_inactive"
    assert poller._parked_count == 0


# ── Sequential polling tests (Task 0.4) ──


def test_next_delay_range():
    """next_delay() возвращает значения в [0.8, 6.0]."""
    from app.userbot.poller import next_delay

    samples = [next_delay() for _ in range(1000)]
    assert all(0.8 <= s <= 6.0 for s in samples), (
        f"All samples must be in [0.8, 6.0]. "
        f"Min: {min(samples):.2f}, Max: {max(samples):.2f}"
    )


def test_next_delay_median():
    """Медиана next_delay() в районе 1.8–2.2 (log-normal с mu=0.7)."""
    from app.userbot.poller import next_delay

    samples = sorted(next_delay() for _ in range(1000))
    median = samples[500]
    assert 1.8 <= median <= 2.2, f"Median should be ~2.0s, got {median:.2f}s"


def test_next_delay_has_spread():
    """Распределение не вырожденное: есть значения и <1.5, и >3.0."""
    from app.userbot.poller import next_delay

    samples = [next_delay() for _ in range(1000)]
    below_15 = sum(1 for s in samples if s < 1.5)
    above_30 = sum(1 for s in samples if s > 3.0)
    assert below_15 > 0, "Should have some fast samples (<1.5s)"
    assert above_30 > 0, "Should have some slow samples (>3.0s)"

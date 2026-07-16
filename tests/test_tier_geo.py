"""Tests for geo-aware tier building — hot tier mirrors _dispatch's geo filter.

Covers:
- _rebuild_tiers: whole-country subscriber → all country channels hot;
  city-scoped country → only city-bound + country-wide channels hot,
  other cities' channels parked; watched channels unaffected.
- _get_active_geo: mode='all' vs mode='cities', empty city list fallback.
- _poll_batch: BudgetExceeded stops the batch (not swallowed per-channel).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.userbot.poller import ChannelPoller
from app.userbot.rate_limiter import BudgetExceeded

VIETNAM, THAILAND = 1, 2
DANANG, NHATRANG, PHUKET = 11, 12, 21


def _ch(username, country_id=None, city_ids=None, watched=False, participants=0):
    return {
        "chat_username": username,
        "country_id": country_id,
        "participants": participants,
        "city_ids": set(city_ids or []),
        "is_watched": watched,
    }


def _make_account(account_id: int, is_healthy: bool = True):
    acc = MagicMock()
    acc.account_id = account_id
    acc.is_healthy = is_healthy
    return acc


async def _rebuild(poller, geo, channels):
    poller._get_active_geo = AsyncMock(return_value=geo)
    poller._get_all_channels = AsyncMock(return_value=channels)
    await poller._rebuild_tiers()


def _hot_names(poller):
    return {c["chat_username"] for c in poller._hot_channels}


# ── _rebuild_tiers ──


@pytest.mark.asyncio
async def test_full_country_sub_makes_all_country_channels_hot():
    poller = ChannelPoller()
    await _rebuild(
        poller,
        ({VIETNAM}, {}),
        [
            _ch("danang_rent", VIETNAM, [DANANG]),
            _ch("nhatrang_bg", VIETNAM, [NHATRANG]),
            _ch("vietnam_bazaar", VIETNAM),
            _ch("phuket_chat", THAILAND, [PHUKET]),
        ],
    )
    assert _hot_names(poller) == {"danang_rent", "nhatrang_bg", "vietnam_bazaar"}
    assert poller._parked_count == 1


@pytest.mark.asyncio
async def test_city_scoped_country_hot_is_city_plus_countrywide():
    """Danang-only subscriber: Danang channels + country-wide hot, Nha Trang parked."""
    poller = ChannelPoller()
    await _rebuild(
        poller,
        (set(), {VIETNAM: {DANANG}}),
        [
            _ch("danang_rent", VIETNAM, [DANANG]),
            _ch("multi_city", VIETNAM, [DANANG, NHATRANG]),
            _ch("nhatrang_bg", VIETNAM, [NHATRANG]),
            _ch("vietnam_bazaar", VIETNAM),  # no city = country-wide
        ],
    )
    assert _hot_names(poller) == {"danang_rent", "multi_city", "vietnam_bazaar"}
    assert poller._parked_count == 1


@pytest.mark.asyncio
async def test_full_country_wins_over_city_scoped():
    """_get_active_geo already collapses; tiers treat full country as all-hot."""
    poller = ChannelPoller()
    await _rebuild(
        poller,
        ({VIETNAM}, {THAILAND: {PHUKET}}),
        [
            _ch("nhatrang_bg", VIETNAM, [NHATRANG]),
            _ch("phuket_chat", THAILAND, [PHUKET]),
            _ch("bangkok_chat", THAILAND, [22]),
        ],
    )
    assert _hot_names(poller) == {"nhatrang_bg", "phuket_chat"}
    assert poller._parked_count == 1


@pytest.mark.asyncio
async def test_watched_channel_outside_active_geo_stays_polled():
    """Watched chats keep Warm/Cold monitoring regardless of subscriptions."""
    poller = ChannelPoller()
    await _rebuild(
        poller,
        (set(), {VIETNAM: {DANANG}}),
        [
            _ch("my_group", None, watched=True, participants=50),
            _ch("my_big_group", THAILAND, watched=True, participants=5000),
        ],
    )
    assert _hot_names(poller) == set()
    assert {c["chat_username"] for c in poller._cold_channels} == {"my_group"}
    assert {c["chat_username"] for c in poller._warm_channels} == {"my_big_group"}


@pytest.mark.asyncio
async def test_no_subscriptions_all_catalog_parked():
    poller = ChannelPoller()
    with patch("app.config.settings.poll_parked_countries", False):
        await _rebuild(
            poller,
            (set(), {}),
            [_ch("danang_rent", VIETNAM, [DANANG]), _ch("vietnam_bazaar", VIETNAM)],
        )
    assert _hot_names(poller) == set()
    assert poller._parked_count == 2


# ── _get_active_geo ──


def _sub_row(sub_id, country_id, mode):
    return (sub_id, country_id, mode)


@pytest.mark.asyncio
async def test_get_active_geo_splits_modes():
    poller = ChannelPoller()
    sub_rows = [
        _sub_row(1, VIETNAM, "cities"),
        _sub_row(2, THAILAND, "all"),
        _sub_row(3, VIETNAM, "cities"),
    ]
    sc_rows = [(1, DANANG), (3, DANANG), (3, NHATRANG)]
    with patch("app.userbot.poller.async_session_factory") as factory:
        session = AsyncMock()
        factory.return_value.__aenter__.return_value = session
        r_subs, r_sc = MagicMock(), MagicMock()
        r_subs.all.return_value = sub_rows
        r_sc.all.return_value = sc_rows
        session.execute.side_effect = [r_subs, r_sc]
        full, city = await poller._get_active_geo()
    assert full == {THAILAND}
    assert city == {VIETNAM: {DANANG, NHATRANG}}


@pytest.mark.asyncio
async def test_get_active_geo_cities_mode_without_rows_counts_as_full():
    """mode='cities' with no city rows = no city filter in _dispatch → full country."""
    poller = ChannelPoller()
    with patch("app.userbot.poller.async_session_factory") as factory:
        session = AsyncMock()
        factory.return_value.__aenter__.return_value = session
        r_subs, r_sc = MagicMock(), MagicMock()
        r_subs.all.return_value = [_sub_row(1, VIETNAM, "cities")]
        r_sc.all.return_value = []
        session.execute.side_effect = [r_subs, r_sc]
        full, city = await poller._get_active_geo()
    assert full == {VIETNAM}
    assert city == {}


@pytest.mark.asyncio
async def test_get_active_geo_full_sub_absorbs_city_subs_same_country():
    poller = ChannelPoller()
    with patch("app.userbot.poller.async_session_factory") as factory:
        session = AsyncMock()
        factory.return_value.__aenter__.return_value = session
        r_subs, r_sc = MagicMock(), MagicMock()
        r_subs.all.return_value = [
            _sub_row(1, VIETNAM, "cities"),
            _sub_row(2, VIETNAM, "all"),
        ]
        r_sc.all.return_value = [(1, DANANG)]
        session.execute.side_effect = [r_subs, r_sc]
        full, city = await poller._get_active_geo()
    assert full == {VIETNAM}
    assert city == {}


# ── BudgetExceeded stops the batch ──


@pytest.mark.asyncio
async def test_budget_exceeded_stops_poll_batch():
    """BudgetExceeded from _poll_channel must halt the batch, not be
    swallowed by the per-channel generic except (the pre-fix bug)."""
    poller = ChannelPoller()
    account = _make_account(1)
    polled = []

    async def _poll_channel(acc, username, tier_name=None, db_title=None):
        polled.append(username)
        raise BudgetExceeded(account_id=1, used=10001, limit=10000)

    poller._poll_channel = _poll_channel
    poller._flush_pending_matches = AsyncMock()

    channels = [_ch(f"chan{i}", VIETNAM) for i in range(5)]
    fake_redis = AsyncMock()
    fake_redis.get.return_value = None
    with (
        patch("app.userbot.poller.get_redis", AsyncMock(return_value=fake_redis)),
        patch("app.worker.notify_admin.notify_admin", AsyncMock()) as notify,
        patch("app.userbot.poller.limiter") as fake_limiter,
    ):
        fake_limiter.is_circuit_open = AsyncMock(return_value=False)
        fake_limiter.wait_if_circuit_open = AsyncMock()
        await poller._poll_batch(account, channels, tier_name="Hot")

    assert len(polled) == 1, "batch must stop after the first BudgetExceeded"
    notify.assert_awaited_once()


# ── Пиннинг каналов к аккаунту (_distribute) ──


@pytest.mark.asyncio
async def test_distribute_pinned_channel_goes_to_member_account():
    """Приватный чат с account_id=2 попадает только аккаунту 2."""
    with patch("app.userbot.poller.limiter") as fake_limiter:
        fake_limiter.is_circuit_open = AsyncMock(return_value=False)
        poller = ChannelPoller()
        poller.pool.accounts = [_make_account(1), _make_account(2)]
        channels = [
            {"chat_username": "-100111", "account_id": 2},
            {"chat_username": "public1", "account_id": None},
            {"chat_username": "public2", "account_id": None},
        ]
        result = await poller._distribute(channels)
    by_acc = {acc.account_id: chunk for acc, chunk in result}
    assert {c["chat_username"] for c in by_acc[2]} >= {"-100111"}
    assert all(c["chat_username"] != "-100111" for c in by_acc[1])
    total = sum(len(chunk) for _, chunk in result)
    assert total == 3


@pytest.mark.asyncio
async def test_distribute_pinned_skipped_when_account_unavailable():
    """Аккаунт-участник заблокирован → его приватные чаты пропускаются, не мигрируют."""
    with patch("app.userbot.poller.limiter") as fake_limiter:
        fake_limiter.is_circuit_open = AsyncMock(side_effect=lambda aid: aid == 2)
        poller = ChannelPoller()
        poller.pool.accounts = [_make_account(1), _make_account(2)]
        channels = [
            {"chat_username": "-100111", "account_id": 2},
            {"chat_username": "public1", "account_id": None},
        ]
        result = await poller._distribute(channels)
    assert len(result) == 1 and result[0][0].account_id == 1
    assert {c["chat_username"] for c in result[0][1]} == {"public1"}


@pytest.mark.asyncio
async def test_distribute_without_account_id_key_unchanged():
    """Каналы без ключа account_id (старый формат) — раздаются как раньше."""
    with patch("app.userbot.poller.limiter") as fake_limiter:
        fake_limiter.is_circuit_open = AsyncMock(return_value=False)
        poller = ChannelPoller()
        poller.pool.accounts = [_make_account(1), _make_account(2)]
        channels = [{"chat_username": f"ch{i}"} for i in range(6)]
        result = await poller._distribute(channels)
    total = sum(len(chunk) for _, chunk in result)
    assert total == 6

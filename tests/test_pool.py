"""Tests for pool degradation behaviour (Task 0.2)."""

from unittest.mock import MagicMock

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
    """После падения acc2 состояние пула не меняется — переброски нет.

    handle_account_failure только логирует. _distribute() в poller.py сам
    разберётся с распределением на следующем цикле. Никакого форсированного
    перераспределения каналов.
    """
    pool = UserbotPool()

    acc1 = _make_account(pool, 1, is_healthy=True)
    acc2 = _make_account(pool, 2, is_healthy=True)
    pool.accounts = [acc1, acc2]

    accounts_before = list(pool.accounts)

    # Симулируем падение acc2
    acc2.is_healthy = False
    await pool.handle_account_failure(acc2)

    # Состав пула не изменился (те же объекты, тот же порядок)
    assert pool.accounts == accounts_before
    # acc2 помечен unhealthy, acc1 всё ещё healthy
    assert not acc2.is_healthy
    assert acc1.is_healthy
    # Нет скрытого перераспределения — метод просто логирует и завершается


@pytest.mark.asyncio
async def test_handle_account_failure_no_exception_when_last_account():
    """При падении последнего живого аккаунта — без исключений."""
    pool = UserbotPool()

    acc1 = _make_account(pool, 1, is_healthy=True)
    pool.accounts = [acc1]

    acc1.is_healthy = False
    # Не должно бросить исключение
    await pool.handle_account_failure(acc1)

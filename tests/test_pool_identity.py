"""Tests for task B1 (fable_audit.md) — explicit account identity.

Bug C5: UserbotPool.initialize numbered accounts by alphabetical order of
session files on disk. Adding discovery.session would shift all IDs →
Redis keys (budgets, circuit breaker, ban counts, sleep windows) would
silently point at the wrong accounts.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.config import settings


# ── userbot_sessions parser ──


def test_session_map_default_parses():
    """Дефолтный маппинг сохраняет прод-идентичность: userbot→1, userbot2→2."""
    with patch.object(settings, "userbot_session_map", "1:userbot,2:userbot2"):
        assert settings.userbot_sessions == {1: "userbot", 2: "userbot2"}


def test_session_map_custom_with_gap():
    """Маппинг с дыркой в ID (аккаунт 2 удалён) валиден."""
    with patch.object(settings, "userbot_session_map", "1:userbot,3:discovery"):
        assert settings.userbot_sessions == {1: "userbot", 3: "discovery"}


def test_session_map_duplicate_id_raises():
    with patch.object(settings, "userbot_session_map", "1:userbot,1:userbot2"):
        with pytest.raises(ValueError):
            _ = settings.userbot_sessions


def test_session_map_empty_name_raises():
    with patch.object(settings, "userbot_session_map", "1:"):
        with pytest.raises(ValueError):
            _ = settings.userbot_sessions


# ── pool.initialize ──


async def _healthy_start(self):
    """Replacement for UserbotAccount.start: mark healthy, no network."""
    self.is_healthy = True


async def _init_pool(tmp_path, session_map: str, files: list[str]):
    """Run UserbotPool.initialize against a temp sessions dir."""
    from app.userbot import pool as pool_mod

    for name in files:
        (tmp_path / f"{name}.session").touch()

    with patch.object(pool_mod, "SESSIONS_DIR", tmp_path), \
         patch.object(pool_mod, "TelegramClient", MagicMock()), \
         patch.object(settings, "userbot_session_map", session_map), \
         patch.object(pool_mod.UserbotAccount, "start", _healthy_start):
        pool = pool_mod.UserbotPool()
        await pool.initialize()
        return pool


async def test_extra_file_does_not_shift_ids(tmp_path):
    """ГЛАВНЫЙ тест C5: файл aaa.session (алфавитно первый) не сдвигает ID.

    Старый код: sorted(files) → aaa=1, userbot=2, userbot2=3 — все Redis-ключи
    поехали бы. Новый: ID берутся из маппинга, aaa игнорируется с warning.
    """
    pool = await _init_pool(
        tmp_path, "1:userbot,2:userbot2",
        files=["aaa", "userbot", "userbot2"],
    )
    by_id = {a.account_id: a.session_name for a in pool.accounts}
    assert by_id == {1: "userbot", 2: "userbot2"}


async def test_missing_session_file_skipped(tmp_path):
    """Аккаунт из маппинга без файла на диске пропускается, остальные живут."""
    pool = await _init_pool(
        tmp_path, "1:userbot,2:userbot2",
        files=["userbot"],  # userbot2.session отсутствует
    )
    by_id = {a.account_id: a.session_name for a in pool.accounts}
    assert by_id == {1: "userbot"}


async def test_all_missing_raises(tmp_path):
    """Ни одного файла из маппинга → RuntimeError (как и раньше при 0 healthy)."""
    with pytest.raises(RuntimeError):
        await _init_pool(tmp_path, "1:userbot,2:userbot2", files=["stranger"])

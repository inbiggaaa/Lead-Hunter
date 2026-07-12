"""A3 (fable_core_plan): карантин сегментов.

Карантинный сегмент продолжает матчиться и логироваться в llm_decisions
(датасет копится), но НЕ диспатчится пользователям. Матч, у которого после
фильтра не осталось сегментов, не уходит в _dispatch; keyword_only-матчи
(личные keywords, «Вариант Б») карантин не задевает никогда.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.userbot.llm_validator import LLMResult, PendingMatch
from app.userbot.poller import ChannelPoller


def _match(segments: list[str], keyword_only: bool = False) -> PendingMatch:
    return PendingMatch(
        chat_username="test_chat",
        message_id=1,
        text="нужен мастер",
        candidate_segments=segments,
        account_id=1,
        keyword_only=keyword_only,
        skip_llm=keyword_only,
    )


async def _flush(poller: ChannelPoller, matches: list[PendingMatch]) -> AsyncMock:
    poller._pending_matches = matches
    dispatch = AsyncMock()
    with patch.object(poller, "_dispatch", dispatch), \
         patch.object(poller, "_log_llm_decision", AsyncMock()), \
         patch("app.userbot.poller.llm_validator") as mock_validator:
        mock_validator.enabled = False
        mock_validator.validate_batch = AsyncMock(
            return_value=[LLMResult(verdict="DEMAND") for _ in matches]
        )
        mock_validator.should_block = lambda r: False
        await poller._flush_pending_matches(account_id=1)
    return dispatch


@pytest.mark.asyncio
async def test_fully_quarantined_match_not_dispatched():
    poller = ChannelPoller()
    poller._quarantined_slugs = {"massage"}
    dispatch = await _flush(poller, [_match(["massage"])])
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_partially_quarantined_dispatches_active_only():
    poller = ChannelPoller()
    poller._quarantined_slugs = {"massage"}
    dispatch = await _flush(poller, [_match(["massage", "fitness"])])
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["matched_segments"] == ["fitness"]


@pytest.mark.asyncio
async def test_no_quarantine_dispatches_all():
    poller = ChannelPoller()
    dispatch = await _flush(poller, [_match(["massage"])])
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["matched_segments"] == ["massage"]


@pytest.mark.asyncio
async def test_keyword_only_match_unaffected_by_quarantine():
    # Личный keyword: candidate_segments пуст — карантин не должен резать
    poller = ChannelPoller()
    poller._quarantined_slugs = {"massage"}
    dispatch = await _flush(poller, [_match([], keyword_only=True)])
    dispatch.assert_awaited_once()


@pytest.mark.asyncio
async def test_quarantined_match_still_logged():
    # Датасет копится: _log_llm_decision вызывается и для карантинного матча
    poller = ChannelPoller()
    poller._quarantined_slugs = {"massage"}
    poller._pending_matches = [_match(["massage"])]
    log_mock = AsyncMock()
    with patch.object(poller, "_dispatch", AsyncMock()), \
         patch.object(poller, "_log_llm_decision", log_mock), \
         patch("app.userbot.poller.llm_validator") as mock_validator:
        mock_validator.enabled = False
        mock_validator.validate_batch = AsyncMock(
            return_value=[LLMResult(verdict="DEMAND")]
        )
        mock_validator.should_block = lambda r: False
        await poller._flush_pending_matches(account_id=1)
    log_mock.assert_awaited_once()


def test_set_seg_maps_builds_quarantined_set():
    class Seg:
        def __init__(self, slug, q):
            self.slug, self.is_quarantined = slug, q
            self.id, self.emoji, self.title_ru, self.title_en = 1, "", slug, slug

    poller = ChannelPoller()
    poller._set_seg_maps([Seg("massage", True), Seg("photo", False)])
    assert poller._quarantined_slugs == {"massage"}

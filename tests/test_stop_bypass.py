"""Tests for task A2 (fable_audit.md) — «?» must not bypass stop-words.

Bug C2: _has_demand_signal returned True for any «?» in the text, and Pass 2
applies stop-words only when there is no demand context. Any ad ending with a
question («Ищешь квартиру? Пиши в ЛС») bypassed ALL stop-words. The same flag
enabled the pre-tag boost in _poll_channel — any question in a pre-tagged
channel became a segment match.

Fix: strong demand (verb patterns, question-word starts, short anchors) still
overrides stop-words; a bare «?» does not. Pass 3 behaviour is unchanged.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from telethon.tl.types import Message

from app.userbot.classifier import classify_message
from app.userbot.poller import ChannelPoller

KEYWORDS = {
    "housing-rent": {
        "demand": ["квартиру", "сдаёт квартиру"],
        "stop": ["пиши в лс"],
        "synonym": [],
    },
}


# ═══ Pass 2: stop-words vs «?» ═══


def test_ad_with_question_mark_is_blocked_by_stop_word():
    """«Ищешь квартиру? Пиши в ЛС» + stop «пиши в лс» → блок (раньше «?» обходил стоп)."""
    result = classify_message(
        "Ищешь квартиру? Пиши в ЛС, подберём лучшие варианты",
        KEYWORDS,
    )
    assert result.matched_segments == []


def test_universal_stop_not_bypassed_by_question_mark():
    """Универсальный stop тоже не обходится «?»."""
    result = classify_message(
        "Хотите квартиру мечты? Наши услуги лучшие на рынке",
        KEYWORDS,
        universal_stops=["наши услуги"],
    )
    assert result.matched_segments == []


def test_strong_demand_still_overrides_stop_word():
    """«Подскажите...» (сильный сигнал) переопределяет stop-слово, как раньше."""
    result = classify_message(
        "Подскажите, кто сдаёт квартиру? Можно в лс",
        {
            "housing-rent": {
                "demand": ["сдаёт квартиру"],
                "stop": ["в лс"],
                "synonym": [],
            },
        },
    )
    assert result.matched_segments == ["housing-rent"]


def test_question_word_start_is_strong_demand():
    """«Где снять квартиру?» — вопросительное слово в начале остаётся сильным сигналом."""
    result = classify_message(
        "Где снять квартиру на месяц? Пиши в лс кто знает",
        KEYWORDS,
    )
    assert result.matched_segments == ["housing-rent"]


def test_plain_demand_without_stop_still_matches():
    """Обычный спрос без stop-слов матчится (регресс)."""
    result = classify_message("Ищу квартиру в центре", KEYWORDS)
    assert result.matched_segments == ["housing-rent"]


# ═══ Pre-tag boost: only strong demand ═══


async def _run_poll(text: str, poller: ChannelPoller):
    entity = MagicMock()
    entity.broadcast = False
    entity.megagroup = True
    entity.title = None
    entity.participants_count = None

    msg = MagicMock(spec=Message)
    msg.id = 7
    msg.message = text
    msg.date = datetime.now(timezone.utc)
    msg.sender = None

    account = MagicMock()
    account.account_id = 1

    with patch.object(poller, "_resolve_entity", new=AsyncMock(return_value=entity)), \
         patch.object(poller, "_fetch_all_since", new=AsyncMock(return_value=[msg])), \
         patch.object(poller, "_get_cursor", new=AsyncMock(return_value=0)), \
         patch.object(poller, "_set_cursor", new=AsyncMock()), \
         patch.object(ChannelPoller, "_log_unmatched", new=AsyncMock()):
        await poller._poll_channel(account, "pretag_chat", tier_name="Hot")


def _pretag_poller() -> ChannelPoller:
    poller = ChannelPoller()
    poller._keyword_map = {
        "manicure": {"demand": ["нерелевантная фраза"], "stop": [], "synonym": []},
    }
    poller._universal_stops = []
    poller._domain_word_map = {}
    poller._personal_keywords = []
    poller._channel_segments = {"pretag_chat": ["manicure"]}
    return poller


async def test_pretag_boost_not_triggered_by_bare_question():
    """Просто вопрос в предтегированном канале — НЕ матч сегмента."""
    poller = _pretag_poller()
    await _run_poll("Открылся новый торговый центр, кому интересно?", poller)
    assert poller._pending_matches == []


async def test_pretag_boost_triggered_by_strong_demand():
    """Сильный спрос в предтегированном канале — матч сегментов канала."""
    poller = _pretag_poller()
    await _run_poll("Подскажите хороший салон в этом районе", poller)
    assert len(poller._pending_matches) == 1
    assert poller._pending_matches[0].candidate_segments == ["manicure"]

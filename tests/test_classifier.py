"""Unit tests for the classifier module."""

import pytest
from app.userbot.classifier import classify_message, ClassificationResult


# Sample keyword map matching seed data
SAMPLE_KEYWORDS = {
    "catering": {
        "demand": [
            "ищу повара", "нужен повар", "ищу шеф-повара",
            "нужен кейтеринг", "заказать кейтеринг",
            "looking for a chef", "need a chef", "need a cook",
        ],
        "stop": [
            "работаю поваром", "я повар", "предлагаю кейтеринг",
            "chef available", "catering services",
        ],
    },
    "massage": {
        "demand": [
            "ищу массажиста", "нужен массаж", "нужен массажист",
            "где массаж", "хочу массаж", "looking for massage",
            "need a massage",
        ],
        "stop": [
            "делаю массаж", "массажист с опытом", "massage available",
        ],
    },
    "bike-rental": {
        "demand": [
            "ищу байк в аренду", "нужен байк в аренду", "сниму байк",
            "аренда байка", "ищу скутер в аренду", "нужен скутер напрокат",
            "хочу арендовать байк", "rent a scooter", "rent a motorbike",
            "looking for bike rental", "need a bike",
        ],
        "stop": [
            "сдаю байк", "сдаю скутер", "bike for rent",
        ],
    },
    "cleaning": {
        "demand": [
            "ищу уборщицу", "нужна уборка", "нужен клининг",
            "looking for cleaning", "need a cleaner",
        ],
        "stop": [
            "предлагаю уборку", "cleaning services",
        ],
    },
}


class TestClassifierBasics:
    """Basic functionality tests."""

    def test_empty_text(self):
        result = classify_message("", SAMPLE_KEYWORDS)
        assert result.matched_segments == []
        assert not result.is_urgent

    def test_empty_keywords(self):
        result = classify_message("ищу повара", {})
        assert result.matched_segments == []

    def test_none_text(self):
        result = classify_message(None, SAMPLE_KEYWORDS)
        assert result.matched_segments == []


class TestDemandMatching:
    """Pass 1: demand phrase matching."""

    def test_exact_demand_match(self):
        result = classify_message("ищу повара на мероприятие", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments

    def test_demand_word_boundary(self):
        # "ищу повара" matches, "повар" alone does not (word boundary)
        result = classify_message("нужен повар", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments

    def test_case_insensitive(self):
        result = classify_message("ИЩУ ПОВАРА", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments

    def test_no_demand_no_match(self):
        result = classify_message("привет как дела", SAMPLE_KEYWORDS)
        assert result.matched_segments == []

    def test_multilingual_demand(self):
        result = classify_message("looking for a chef in Danang", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments

    def test_demand_unicode(self):
        result = classify_message("нужен массаж в Нячанге", SAMPLE_KEYWORDS)
        assert "massage" in result.matched_segments

    def test_multiple_segments(self):
        result = classify_message("ищу повара и нужен массаж", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments
        assert "massage" in result.matched_segments
        assert len(result.matched_segments) == 2


class TestStopPhrases:
    """Pass 2: stop-phrase blocking."""

    def test_offer_stop_suppresses(self):
        result = classify_message("я повар предлагаю кейтеринг", SAMPLE_KEYWORDS)
        # "я повар" and "предлагаю кейтеринг" are stop phrases → should not match
        assert "catering" not in result.matched_segments

    def test_universal_stop(self):
        result = classify_message(
            "ищу повара, записывайтесь ко мне",
            SAMPLE_KEYWORDS,
            universal_stops=["записывайтесь"],
        )
        # "записывайтесь" is universal stop + demand matched → demand signal overrides
        assert "catering" in result.matched_segments

    def test_demand_signal_overrides_stop(self):
        result = classify_message(
            "ищу повара, принимаю у себя",
            SAMPLE_KEYWORDS,
            universal_stops=["принимаю у себя"],
        )
        # "принимаю у себя" is universal stop, but "ищу" is strong demand signal
        assert "catering" in result.matched_segments


class TestUrgency:
    """Urgency detection (🔥)."""

    def test_srochno(self):
        result = classify_message("срочно ищу повара", SAMPLE_KEYWORDS)
        assert result.is_urgent

    def test_segodnya(self):
        result = classify_message("нужен повар сегодня", SAMPLE_KEYWORDS)
        assert result.is_urgent

    def test_asap(self):
        result = classify_message("need a chef asap", SAMPLE_KEYWORDS)
        assert result.is_urgent

    def test_no_urgency(self):
        result = classify_message("ищу повара на следующей неделе", SAMPLE_KEYWORDS)
        assert not result.is_urgent


class TestStructuralSignals:
    """Pass 3: demand vs offer signals."""

    def test_demand_verb_at_start(self):
        result = classify_message("ищу повара цена 1000", SAMPLE_KEYWORDS)
        # Strong demand verb at start overrides price signal
        assert "catering" in result.matched_segments

    def test_question_mark_boosts_demand(self):
        # Question mark strengthens demand but there must be a keyword match
        result = classify_message("ищу повара?", SAMPLE_KEYWORDS)
        assert "catering" in result.matched_segments

    def test_offer_without_demand_suppressed(self):
        result = classify_message("массаж цена 500 записывайтесь", SAMPLE_KEYWORDS)
        assert "massage" not in result.matched_segments


class TestShortAnchors:
    """Short anchor matching — only with contextual demand signal.

    Short anchors (e.g. 'нужен байк') are high-risk phrases that match
    ONLY when a demand signal is present. They work as context signals
    in _has_demand_signal(), not as direct keyword matchers.
    Segment-specific short anchor matching will be implemented
    when short_anchor keyword_type is added to segment_keywords.
    """

    def test_short_anchor_with_demand_signal_enables_match(self):
        # Strong demand verb 'ищу' + keyword = match
        result = classify_message("посоветуйте, ищу байк в аренду", SAMPLE_KEYWORDS)
        assert "bike-rental" in result.matched_segments

    def test_short_anchor_alone_no_match(self):
        # 'нужен байк' alone is not a demand keyword
        result = classify_message("нужен байк", SAMPLE_KEYWORDS)
        assert "bike-rental" not in result.matched_segments

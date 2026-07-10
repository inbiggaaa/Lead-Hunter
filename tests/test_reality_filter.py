"""C3: reality-фильтр (_filter_by_domain) на word-boundary вместо substring.

Substring-проверка давала ложные подтверждения: domain-слово «спа» находилось
внутри «спасибо», «мани» — внутри «Германии». Теперь — _match_keyword
(word-boundary, Unicode, негация). Политика «сегмент без domain-слов проходит»
сохранена, но дыра стала видимой через logger.debug.
"""

import logging

from app.userbot.poller import ChannelPoller


def _make_poller(domain_map: dict) -> ChannelPoller:
    poller = ChannelPoller()
    poller._domain_word_map = domain_map
    return poller


def test_substring_false_positive_blocked():
    # «спа» НЕ должно подтверждаться словом «спасибо»
    poller = _make_poller({"massage": ["спа"]})
    assert poller._filter_by_domain("спасибо за информацию", ["massage"]) == []


def test_word_boundary_hit_passes():
    poller = _make_poller({"massage": ["спа"]})
    assert poller._filter_by_domain(
        "ищу спа салон в дананге", ["massage"]
    ) == ["massage"]


def test_case_insensitive():
    poller = _make_poller({"massage": ["спа"]})
    assert poller._filter_by_domain("Хочу СПА процедуры", ["massage"]) == ["massage"]


def test_multiword_domain_synonym():
    poller = _make_poller({"cargo": ["доставка грузов"]})
    assert poller._filter_by_domain(
        "нужна доставка моих грузов в ханой", ["cargo"]
    ) == ["cargo"]
    assert poller._filter_by_domain("нужна доставка еды", ["cargo"]) == []


def test_segment_without_domain_words_passes(caplog):
    poller = _make_poller({})
    with caplog.at_level(logging.DEBUG, logger="app.userbot.poller"):
        result = poller._filter_by_domain("любой текст", ["visa-support"])
    assert result == ["visa-support"]
    assert any("visa-support" in r.message for r in caplog.records)


def test_mixed_segments():
    poller = _make_poller({"massage": ["спа"], "cargo": ["груз"]})
    assert poller._filter_by_domain(
        "спасибо, ищу перевозку: есть груз до Ханоя", ["massage", "cargo"]
    ) == ["cargo"]

"""Экран «Мои каналы»: человекочитаемые названия вместо сырых -100…-ID.

Bulk-вставленные группы (chat_username = внутренний ID) имеют title в БД —
показываем его; для публичных каналов title дополняется @username; голый ID —
только когда названия нет совсем.
"""

from types import SimpleNamespace

from app.bot.handlers.channels import _channel_label


def _ch(username: str, title: str | None) -> SimpleNamespace:
    return SimpleNamespace(chat_username=username, title=title)


def test_numeric_id_with_title_shows_title_only():
    ch = _ch("-1001729342091", "Испания 🇪🇸 Чат TravelAsk")
    assert _channel_label(ch) == "Испания 🇪🇸 Чат TravelAsk"


def test_public_with_title_shows_title_and_username():
    ch = _ch("danang_chat", "Дананг Чат")
    assert _channel_label(ch) == "Дананг Чат (@danang_chat)"


def test_public_without_title_shows_username():
    assert _channel_label(_ch("my_leadalert_test_xxx", None)) == "@my_leadalert_test_xxx"


def test_numeric_without_title_shows_group_id():
    assert _channel_label(_ch("-1001234567890", "")) == "группа -1001234567890"


def test_label_truncated():
    ch = _ch("-100123", "Очень длинное название чата которое не влезает в кнопку никак")
    assert len(_channel_label(ch, max_len=25)) == 25

import pytest

from app.locales import EN, RU, get_text, normalize_language, template_fields, validate_locale_schema
from app.worker.sender import NotificationSender


def test_locale_keys_and_placeholders_match():
    validate_locale_schema()
    assert RU.keys() == EN.keys()
    for key in RU:
        assert template_fields(RU[key]) == template_fields(EN[key])


def test_invalid_language_falls_back_to_russian():
    assert normalize_language("xx") == "ru"
    assert get_text("xx", "btn_back") == RU["btn_back"]


def test_unknown_key_is_not_rendered_to_user():
    with pytest.raises(KeyError):
        get_text("ru", "missing_key")


def _payload(lang):
    return {"lang": lang, "plan": "free", "chat_username": "testchat", "chat_title": "Test chat", "message_id": 1, "text": "Need a contractor", "matched_segments": [{"emoji": "🔧", "title": "Repair"}]}


def test_sender_ru_en_semantic_parity():
    sender = NotificationSender()
    try:
        ru = sender._format_notification(_payload("ru"))
        en = sender._format_notification(_payload("en"))
        assert "платный тариф" in ru
        assert "paid plan" in en
        assert "Need a contractor" in ru and "Need a contractor" in en
        assert sender._build_keyboard(_payload("ru")).inline_keyboard[1][0].text.startswith("🎯 Открыть")
        assert sender._build_keyboard(_payload("en")).inline_keyboard[1][0].text.startswith("🎯 Unlock")
        ru_cb = sender._build_keyboard({**_payload("ru"), "_lead_token": "abc123"}).inline_keyboard[1][0].callback_data
        assert ru_cb == "lead:unlock:abc123" and len(ru_cb.encode()) <= 64
    finally:
        import asyncio
        asyncio.run(sender.bot.session.close())

"""U10 text-and-keyboard snapshots for the complete localized user flow."""

import asyncio
import re
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from app.bot.handlers.plan import build_paywall, build_plan_screen, payment_error_kb
from app.locales import EN, RU, get_text, template_fields, validate_locale_schema
from app.worker.end_of_day import _report_keyboard
from app.worker.reminders import _offer_keyboard, _reminder_kb, _upgrade_kb
from app.worker.sender import NotificationSender

MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024
CALLBACK_LIMIT = 64
ALLOWED_HTML_TAGS = frozenset({"a", "b", "blockquote", "code", "em", "i", "pre", "s", "strong", "u"})
LANGUAGE_PICKER_KEYS = frozenset({"btn_ru", "welcome_title", "welcome_body", "welcome_lang_prompt"})
DENIED_CLAIMS = (
    "заявка за 2 секунды",
    "гарантированный поток заявок",
    "клиент уже выбрал конкурента",
    "самый популярный тариф",
    "лимит уведомлений исчерпан",
    "lead in 2 seconds",
    "guaranteed flow of leads",
    "client has already chosen a competitor",
    "most popular plan",
    "notification limit reached",
)
SAMPLE_VALUES = {
    "activated": 2,
    "bonus": 10,
    "bonus_days": 20,
    "category": "Home services",
    "chat": "Test chat",
    "channel": "test_channel",
    "channels": 120,
    "cities": "Moscow, Kazan",
    "count": 3,
    "countries": 9,
    "country": "Russia",
    "current": 1,
    "date": "20.07.2026",
    "days": 30,
    "delivered": 2,
    "expires": "20.07.2026 12:00 UTC",
    "invited": 4,
    "item": "looking for a designer",
    "labels": "Design",
    "limit": 9,
    "link": "https://t.me/LeadHunterBot?start=ref_TEST",
    "matched": 4,
    "missed": 2,
    "monthly": 15,
    "monthly_total": 228,
    "name": "Pro",
    "period": "3 months",
    "plan": "Pro",
    "preview": "Looking for a designer",
    "price": 19,
    "reason": "provider_offer",
    "confirmed": "cleaning",
    "expected": "repair",
    "verdict": "error",
    "label": "error/provider_offer",
    "referral_bonus": 4,
    "remaining": 8,
    "savings": 6,
    "sender": "client",
    "start": 9,
    "total": 51,
    "trial_days": 7,
    "year_total": 182,
}


class TelegramHTMLValidator(HTMLParser):
    """Validate the small HTML subset accepted by Telegram parse_mode=HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        assert tag in ALLOWED_HTML_TAGS, f"unsupported HTML tag: {tag}"
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack, f"closing tag without opener: {tag}"
        assert self.stack.pop() == tag, f"unbalanced HTML tag: {tag}"

    def assert_complete(self) -> None:
        assert not self.stack, f"unclosed HTML tags: {self.stack}"


def _render_locale(locale: dict[str, str]) -> dict[str, str]:
    snapshots = {}
    for key, template in locale.items():
        values = {field: SAMPLE_VALUES[field] for field in template_fields(template)}
        snapshots[key] = template.format(**values)
    return snapshots


def _keyboard_snapshot(keyboard) -> list[list[dict[str, str]]]:
    return [[button.model_dump(exclude_none=True) for button in row] for row in keyboard.inline_keyboard]


def _assert_keyboard(keyboard) -> None:
    snapshot = _keyboard_snapshot(keyboard)
    assert snapshot
    for row in snapshot:
        assert row
        for button in row:
            assert button["text"].strip()
            callback = button.get("callback_data")
            if callback:
                assert len(callback.encode("utf-8")) <= CALLBACK_LIMIT


def _assert_html(text: str) -> None:
    validator = TelegramHTMLValidator()
    validator.feed(text)
    validator.close()
    validator.assert_complete()


def _lead_payload(lang: str, plan: str, chat_username: str) -> dict[str, object]:
    return {
        "lang": lang,
        "plan": plan,
        "chat_username": chat_username,
        "chat_title": "Private Clients",
        "message_id": 42,
        "sender_username": "client_name",
        "text": "Looking for a contractor",
        "matched_segments": [{"emoji": "🔧", "title": "Repair"}],
        "_lead_token": "lead-token-42",
    }


def test_u10_locale_snapshots_are_renderable_and_safe() -> None:
    validate_locale_schema()
    snapshots = {"ru": _render_locale(RU), "en": _render_locale(EN)}

    for lang, screens in snapshots.items():
        assert screens.keys() == RU.keys()
        for key, text in screens.items():
            assert text.strip(), f"empty {lang} snapshot: {key}"
            assert len(text) <= MESSAGE_LIMIT, f"oversized {lang} snapshot: {key}"
            assert not template_fields(text), f"unresolved placeholder in {lang}.{key}"
            _assert_html(text)
            lowered = text.casefold()
            assert not any(claim in lowered for claim in DENIED_CLAIMS), f"denied claim in {lang}.{key}"

    for key, text in snapshots["en"].items():
        if key not in LANGUAGE_PICKER_KEYS:
            assert not re.search(r"[А-Яа-яЁё]", text), f"Cyrillic in EN snapshot: {key}"


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("plan", ["free", "start", "pro", "business", "trial"])
def test_u10_plan_screen_snapshots(lang: str, plan: str) -> None:
    text, keyboard = build_plan_screen(SimpleNamespace(plan=plan), lang)

    assert len(text) <= MESSAGE_LIMIT
    _assert_html(text)
    _assert_keyboard(keyboard)
    assert keyboard.inline_keyboard[-1][0].callback_data == "menu:main"
    assert [row[0].callback_data for row in keyboard.inline_keyboard[:-1]] == [
        "pay_plan:start", "pay_plan:pro", "pay_plan:business"
    ]


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("trigger", ["keyword", "direction", "country", "city", "channel", "stats", "csv"])
@pytest.mark.parametrize("current_plan", ["free", "start", "pro"])
def test_u10_paywall_snapshots(lang: str, trigger: str, current_plan: str) -> None:
    text, keyboard = build_paywall(trigger, current_plan, lang)

    assert len(text) <= MESSAGE_LIMIT
    _assert_html(text)
    _assert_keyboard(keyboard)
    assert keyboard.inline_keyboard[-1][0].callback_data == "menu:main"
    assert keyboard.inline_keyboard[0][0].callback_data.startswith("pay_plan:")


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("method", ["stars", "crypto"])
def test_u10_payment_error_snapshots(lang: str, method: str) -> None:
    keyboard = payment_error_kb("pro", "3m", method, lang)

    _assert_keyboard(keyboard)
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        f"pay_exec:{method}:pro:3m", "pay_period:pro:3m", "pay_plan:pro"
    ]


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_u10_lifecycle_keyboard_snapshots(lang: str) -> None:
    keyboards = (
        _upgrade_kb(lang),
        _reminder_kb("trial_ending", "trial", lang),
        _reminder_kb("subscription_ending", "start", lang),
        _offer_keyboard(lang),
        _report_keyboard(lang),
    )

    for keyboard in keyboards:
        assert keyboard is not None
        _assert_keyboard(keyboard)


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("plan", ["free", "start", "pro", "business", "trial"])
@pytest.mark.parametrize("chat_username", ["public_chat", "-1002046178126"])
def test_u10_lead_snapshots_preserve_visibility_contract(
    lang: str, plan: str, chat_username: str
) -> None:
    sender = NotificationSender()
    payload = _lead_payload(lang, plan, chat_username)
    try:
        text = sender._format_notification(payload)
        keyboard = sender._build_keyboard(payload)
        assert len(text) <= MESSAGE_LIMIT
        _assert_html(text)
        _assert_keyboard(keyboard)
        if plan == "free":
            assert "https://t.me/" not in text
            assert all(not button.url for row in keyboard.inline_keyboard for button in row)
            assert any(button.callback_data == "lead:unlock:lead-token-42" for row in keyboard.inline_keyboard for button in row)
        else:
            assert "Private Clients" in text
            assert any(button.url for row in keyboard.inline_keyboard for button in row)
    finally:
        asyncio.run(sender.bot.session.close())


def test_u10_welcome_caption_fits_telegram_limit() -> None:
    for lang in ("ru", "en"):
        caption = "\n\n".join((
            get_text(lang, "welcome_title"),
            get_text(lang, "welcome_body"),
            get_text(lang, "welcome_lang_prompt"),
        ))
        assert len(caption) <= CAPTION_LIMIT
        _assert_html(caption)

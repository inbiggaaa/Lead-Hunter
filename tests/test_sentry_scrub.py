"""Unit tests for Sentry PII / lead-text scrubbing."""

from app.sentry_setup import before_send


def test_before_send_redacts_lead_keys():
    event = {
        "extra": {
            "text": "ищу повара в Нячанге срочно сегодня бюджет 200",
            "user_id": 42,
        },
        "exception": {
            "values": [{"value": "x" * 400}],
        },
    }
    out = before_send(event)
    assert out is not None
    assert out["extra"]["text"] == "[redacted]"
    assert out["extra"]["user_id"] == 42
    assert out["exception"]["values"][0]["value"].endswith("…[redacted]")


def test_before_send_keeps_short_safe_fields():
    event = {"extra": {"plan": "pro", "service": "worker"}}
    out = before_send(event)
    assert out["extra"]["plan"] == "pro"

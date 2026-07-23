"""API smoke tests for matching feedback endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admin.api.matching_feedback import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_summary_endpoint(client):
    fake = {"batch": "ru_matching_v1", "delivered": 2, "precision": 1.0}
    with patch(
        "app.admin.api.matching_feedback.build_feedback_summary",
        new=AsyncMock(return_value=fake),
    ):
        resp = client.get("/api/matching-feedback/summary", params={"batch": "ru_matching_v1"})
    assert resp.status_code == 200
    assert resp.json()["precision"] == 1.0


def test_export_jsonl_endpoint(client):
    rows = [
        {
            "test_batch": "ru_matching_v1",
            "chat_username": "c",
            "message_id": 1,
            "message_text_masked": "x",
            "delivered_segments": ["cleaning"],
            "verdict": "correct",
            "confirmed_segments": ["cleaning"],
            "reason_code": None,
            "expected_segment_slug": None,
            "expected_segment_missing": False,
            "legacy_llm_verdict": "DEMAND",
            "v2_intent": None,
            "model_name": "deepseek-chat",
            "prompt_version": 2,
            "schema_version": 2,
            "profile_versions": {},
        }
    ]
    with patch(
        "app.admin.api.matching_feedback.list_feedback_rows",
        new=AsyncMock(return_value=rows),
    ):
        resp = client.get(
            "/api/matching-feedback/export.jsonl",
            params={"batch": "ru_matching_v1"},
        )
    assert resp.status_code == 200
    assert "correct" in resp.text
    assert "telegram_id" not in resp.text

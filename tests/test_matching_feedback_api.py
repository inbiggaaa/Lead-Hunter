"""API smoke tests for matching feedback endpoints (no httpx dependency)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.admin.api import matching_feedback as api
from app.matching_feedback.analytics import export_feedback_jsonl_bytes


@pytest.mark.asyncio
async def test_summary_endpoint():
    fake = {"batch": "ru_matching_v1", "delivered": 2, "precision": 1.0}
    with patch.object(api, "build_feedback_summary", new=AsyncMock(return_value=fake)):
        result = await api.matching_feedback_summary(batch="ru_matching_v1")
    assert result["precision"] == 1.0


@pytest.mark.asyncio
async def test_export_jsonl_endpoint():
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
    with patch.object(api, "list_feedback_rows", new=AsyncMock(return_value=rows)):
        resp = await api.matching_feedback_export_jsonl(batch="ru_matching_v1")
    body = resp.body.decode("utf-8")
    assert "correct" in body
    assert "telegram_id" not in body
    assert export_feedback_jsonl_bytes(rows).decode("utf-8") == body

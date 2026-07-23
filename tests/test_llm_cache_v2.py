"""Phase 6: LLM verdict cache key v2."""

from __future__ import annotations

from app.userbot.llm_prompt import RESPONSE_SCHEMA_VERSION, SYSTEM_PROMPT_VERSION
from app.userbot.llm_validator import _llm_cache_key, build_llm_cache_key, normalize_llm_cache_text


def _base(**overrides):
    payload = {
        "text": "ищу тренера по теннису",
        "candidate_segments": ("tennis",),
        "lead_directions": {"tennis": "demand"},
        "profile_versions": {"tennis": 1},
        "prompt_version": SYSTEM_PROMPT_VERSION,
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "model_name": "deepseek-chat",
    }
    payload.update(overrides)
    return build_llm_cache_key(**payload)


def test_candidate_order_does_not_change_key():
    a = build_llm_cache_key(
        text="нужен сантехник",
        candidate_segments=("plumber", "electrician"),
        lead_directions={"plumber": "demand", "electrician": "demand"},
        profile_versions={"plumber": 1, "electrician": 1},
        prompt_version=2,
        schema_version=2,
        model_name="deepseek-chat",
    )
    b = build_llm_cache_key(
        text="нужен сантехник",
        candidate_segments=("electrician", "plumber"),
        lead_directions={"electrician": "demand", "plumber": "demand"},
        profile_versions={"electrician": 1, "plumber": 1},
        prompt_version=2,
        schema_version=2,
        model_name="deepseek-chat",
    )
    assert a == b


def test_different_candidate_changes_key():
    assert _base(candidate_segments=("tennis",)) != _base(
        candidate_segments=("fitness",),
        lead_directions={"fitness": "demand"},
        profile_versions={"fitness": 1},
    )


def test_different_lead_direction_changes_key():
    assert _base(lead_directions={"tennis": "demand"}) != _base(
        lead_directions={"tennis": "supply"}
    )


def test_different_profile_version_changes_key():
    assert _base(profile_versions={"tennis": 1}) != _base(
        profile_versions={"tennis": 2}
    )


def test_prompt_version_changes_key():
    assert _base(prompt_version=2) != _base(prompt_version=3)


def test_schema_version_changes_key():
    assert _base(schema_version=2) != _base(schema_version=3)


def test_model_changes_key():
    assert _base(model_name="deepseek-chat") != _base(model_name="deepseek-reasoner")


def test_whitespace_case_normalization_deterministic():
    a = build_llm_cache_key(
        text="Ищу   Тренера\nпо теннису",
        candidate_segments=("tennis",),
        lead_directions={"tennis": "demand"},
        profile_versions={"tennis": 1},
        prompt_version=2,
        schema_version=2,
        model_name="deepseek-chat",
    )
    b = build_llm_cache_key(
        text="ищу тренера по теннису",
        candidate_segments=("tennis",),
        lead_directions={"tennis": "demand"},
        profile_versions={"tennis": 1},
        prompt_version=2,
        schema_version=2,
        model_name="deepseek-chat",
    )
    assert a == b
    assert normalize_llm_cache_text("Ищу   Тренера\nпо теннису") == "ищу тренера по теннису"


def test_no_raw_message_text_in_redis_key():
    key = _base(text="секретный текст лида с телефоном")
    assert key.startswith("llm:v2:verdict:")
    assert "секретный" not in key
    assert "телефоном" not in key
    digest = key.split(":")[-1]
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_old_namespace_not_reused():
    v2 = _base()
    v1 = _llm_cache_key("ищу тренера по теннису")
    assert v2.startswith("llm:v2:verdict:")
    assert v1.startswith("llm:verdict:")
    assert not v1.startswith("llm:v2:")
    assert v2 != v1

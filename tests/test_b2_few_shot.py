"""B2 — curated few-shot block in LLM system prompt."""

from app.userbot.llm_validator import (
    FEW_SHOT_EXAMPLES,
    LLM_SYSTEM_PROMPT,
    build_system_prompt,
)


def test_few_shot_count_bounded():
    assert 4 <= len(FEW_SHOT_EXAMPLES) <= 6


def test_few_shot_covers_demand_and_noise():
    verdicts = {v for _, _, v, _ in FEW_SHOT_EXAMPLES}
    assert "DEMAND" in verdicts
    assert "OFFER" in verdicts
    assert "OTHER" in verdicts


def test_default_prompt_includes_calibration():
    assert "CALIBRATION" in LLM_SYSTEM_PROMPT
    assert "обмен USDT" in LLM_SYSTEM_PROMPT
    assert "нужен сантехник сегодня" in LLM_SYSTEM_PROMPT


def test_can_build_prompt_without_few_shot():
    prompt = build_system_prompt(set(), include_few_shot=False)
    assert "CALIBRATION" not in prompt
    assert "DEMAND" in prompt


def test_few_shot_token_growth_under_30_percent():
    """Character proxy for prompt_tokens — few-shot must stay ≤30% of base."""
    base = build_system_prompt({"moto-purchase", "car-purchase"}, include_few_shot=False)
    full = build_system_prompt({"moto-purchase", "car-purchase"}, include_few_shot=True)
    growth = (len(full) - len(base)) / len(base)
    assert growth <= 0.30, f"few-shot grew prompt by {growth:.1%}"

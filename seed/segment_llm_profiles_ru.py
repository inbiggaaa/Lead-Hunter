"""Approved RU segment LLM profiles (Phase 2).

Source of truth for import: seed/data/segment_llm_profiles_ru.json
(hand-approved extract from docs/semantic/keyword_profiles_ru_v1.md).

Do NOT parse Markdown at runtime. Do NOT auto-apply to production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILES_JSON = Path(__file__).resolve().parent / "data" / "segment_llm_profiles_ru.json"


def profiles_json_path() -> Path:
    return PROFILES_JSON


def load_profile_seed(path: Path | None = None) -> dict[str, Any]:
    target = path or PROFILES_JSON
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "profiles" not in raw:
        raise ValueError(f"Invalid profile seed file: {target}")
    return raw


def load_profiles(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_profile_seed(path)["profiles"])

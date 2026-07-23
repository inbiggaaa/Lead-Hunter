"""Print segment-profile enablement status (Phase 11). Does not mutate prod.

Usage:
  venv/bin/python tools/check_segment_profile_enablement.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.userbot.llm_validator import FIRST_WAVE_BLOCKING_SEGMENTS  # noqa: E402


def main() -> int:
    allow = settings.blocking_segment_allowlist()
    print("LLM segment-profile enablement")
    print(f"  llm_enabled                      = {settings.llm_enabled}")
    print(f"  llm_mode                         = {settings.llm_mode}")
    print(f"  llm_segment_profiles_enabled     = {settings.llm_segment_profiles_enabled}")
    print(f"  llm_segment_profiles_blocking    = {settings.llm_segment_profiles_blocking}")
    print(
        f"  llm_segment_profiles_blocking_segments = "
        f"{settings.llm_segment_profiles_blocking_segments!r}"
    )
    print(f"  parsed allowlist                 = {sorted(allow) or '(empty = fail-safe)'}")
    print(f"  first-wave constant              = {sorted(FIRST_WAVE_BLOCKING_SEGMENTS)}")

    delivery = "legacy only"
    if settings.llm_segment_profiles_enabled and not settings.llm_segment_profiles_blocking:
        delivery = "shadow (v2 metrics, legacy delivery)"
    elif settings.llm_segment_profiles_enabled and settings.llm_segment_profiles_blocking:
        if not allow:
            delivery = "BLOCKING FLAG ON but allowlist empty → still legacy delivery"
        elif "*" in allow:
            delivery = "v2 blocking for ALL segments"
        else:
            delivery = f"v2 blocking for allowlist only: {sorted(allow)}"
    print(f"  effective delivery               = {delivery}")
    print()
    print("Runbook: docs/ops/segment_profiles_enablement_ru.md")
    print("Rollback blocking: LLM_SEGMENT_PROFILES_BLOCKING=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

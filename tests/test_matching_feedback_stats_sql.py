"""Stats API query mapping for closed matching feedback verdicts."""

from __future__ import annotations

import ast
from pathlib import Path


def test_segment_feedback_sql_uses_correct_error_taxonomy():
    src = Path("app/admin/api/stats.py").read_text(encoding="utf-8")
    assert "verdict IN ('correct', 'relevant')" in src
    assert "verdict IN ('error', 'not_relevant')" in src
    assert "f.delivered_segments" in src
    # Legacy-only filter must not be the sole path
    assert "WHERE x.verdict = 'relevant'" not in src
    assert "WHERE f.verdict = 'not_relevant'" not in src


def test_stats_module_parses():
    src = Path("app/admin/api/stats.py").read_text(encoding="utf-8")
    ast.parse(src)

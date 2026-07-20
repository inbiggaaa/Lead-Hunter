#!/usr/bin/env python3
"""List quarantine candidates from live feedback (≥5 votes, precision <20%).

Read-only. Does NOT set is_quarantined — owner toggles in admin /catalog.

Usage:
  PYTHONPATH=. venv/bin/python tools/quarantine_candidates.py [--days 30]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.db.session import async_session_factory


SQL = text(
    """
    SELECT x.slug,
           count(*) FILTER (WHERE x.verdict = 'relevant')     AS relevant,
           count(*) FILTER (WHERE x.verdict = 'not_relevant') AS not_relevant,
           s.is_quarantined
    FROM (
        SELECT f.verdict,
               unnest(coalesce(nullif(d.llm_segments, '{}'), d.rule_segments)) AS slug
        FROM feedback f
        JOIN LATERAL (
            SELECT llm_segments, rule_segments
            FROM llm_decisions d
            WHERE d.chat_username = f.chat_username
              AND d.message_id = f.message_id
            ORDER BY d.id DESC LIMIT 1
        ) d ON true
        WHERE f.created_at > now() - make_interval(days => :days)
    ) x
    JOIN segments s ON s.slug = x.slug
    GROUP BY x.slug, s.is_quarantined
    ORDER BY not_relevant DESC, relevant ASC
    """
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--min-votes", type=int, default=5)
    parser.add_argument("--max-precision", type=float, default=0.20)
    args = parser.parse_args()

    async with async_session_factory() as session:
        rows = (await session.execute(SQL, {"days": args.days})).all()

    if not rows:
        print("No feedback joined to llm_decisions in window — empty DB or no data.")
        return

    print(f"# Quarantine candidates (last {args.days}d)")
    print(f"# Rule: votes≥{args.min_votes} and precision<{args.max_precision:.0%}")
    print(f"{'slug':32} {'👍':>4} {'👎':>4} {'prec':>6} {'status'}")
    candidates = 0
    for r in rows:
        total = int(r.relevant) + int(r.not_relevant)
        if total == 0:
            continue
        prec = int(r.relevant) / total
        flag = ""
        if total >= args.min_votes and prec < args.max_precision:
            flag = "CANDIDATE"
            candidates += 1
        if r.is_quarantined:
            flag = (flag + "+QUARANTINED").strip("+")
        if flag:
            print(f"{r.slug:32} {r.relevant:4} {r.not_relevant:4} {prec:6.1%} {flag}")

    print(f"\nCandidates: {candidates}")
    print("Apply quarantine only in admin /catalog (manual). Do not auto-toggle.")


if __name__ == "__main__":
    asyncio.run(main())

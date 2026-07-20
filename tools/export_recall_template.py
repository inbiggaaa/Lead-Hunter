#!/usr/bin/env python3
"""Export a fresh 100-row recall labeling template from Redis unmatched.

Read-only. Owner fills FN?/Segment columns → docs/eval/recall_YYYY-MM.md.

Usage:
  PYTHONPATH=. venv/bin/python tools/export_recall_template.py
  PYTHONPATH=. venv/bin/python tools/export_recall_template.py --limit 100 --stride 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from redis.asyncio import Redis

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.eval_matching import _read_env  # noqa: E402

OUT_DIR = PROJECT_ROOT / "docs" / "eval"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--stride", type=int, default=3, help="Take every Nth entry for chat diversity")
    args = parser.parse_args()

    env = _read_env(PROJECT_ROOT / ".env")
    host = env.get("REDIS_HOST", "127.0.0.1")
    port = int(env.get("REDIS_PORT", "6379"))
    db = int(env.get("REDIS_DB", "0"))
    redis = Redis(host=host, port=port, db=db, decode_responses=True)
    try:
        raw = await redis.lrange("stats:unmatched", 0, args.limit - 1)
    finally:
        await redis.aclose()

    rows = []
    for i, item in enumerate(raw):
        if i % args.stride != 0:
            continue
        try:
            obj = json.loads(item) if isinstance(item, str) else item
        except json.JSONDecodeError:
            continue
        text = (obj.get("text") or "").replace("|", "/").replace("\n", " ")
        chat = obj.get("chat_username") or obj.get("chat") or ""
        rows.append((chat, text[:180]))
        if len(rows) >= args.sample:
            break

    stamp = date.today().isoformat()
    out = OUT_DIR / f"recall_template_{stamp}.md"
    lines = [
        f"# Recall labeling template — {stamp}",
        "",
        "Fill columns **FN?** (yes/no) and **Segment** (slug or —).",
        "Then compute FN-rate in `docs/eval/recall_YYYY-MM.md`.",
        "",
        "| # | Chat | Text | FN? | Segment |",
        "|---|---|---|---|---|",
    ]
    for i, (chat, text) in enumerate(rows, 1):
        lines.append(f"| {i} | @{chat} | {text} | | |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(rows)} rows)")
    if len(rows) < args.sample:
        print(f"WARNING: only {len(rows)} unmatched available (wanted {args.sample})")


if __name__ == "__main__":
    asyncio.run(main())

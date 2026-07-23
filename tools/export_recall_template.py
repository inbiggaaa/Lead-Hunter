#!/usr/bin/env python3
"""Export a masked recall labeling sample for a closed matching feedback batch.

Each batch gets a file-based artifact (not a runtime table):
  - 50 unmatched messages from Redis stats:unmatched
  - 50 LLM-rejected messages from llm_decisions (OFFER/OTHER)

Manual columns: missed_lead, expected_segment, missed_at_layer.

Usage:
  PYTHONPATH=. venv/bin/python tools/export_recall_template.py --batch ru_matching_v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from datetime import date
from pathlib import Path

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.eval_matching import _read_env  # noqa: E402
from app.matching_feedback.domain import mask_message_text  # noqa: E402

OUT_DIR = PROJECT_ROOT / "docs" / "eval"


async def _sample_unmatched(redis: Redis, n: int) -> list[dict]:
    raw = await redis.lrange("stats:unmatched", 0, 5000)
    rows = []
    for item in raw:
        try:
            obj = json.loads(item) if isinstance(item, str) else item
        except json.JSONDecodeError:
            continue
        text_raw = obj.get("text") or ""
        rows.append(
            {
                "source": "unmatched",
                "chat_username": obj.get("chat_username") or obj.get("chat") or "",
                "message_text_masked": mask_message_text(text_raw),
            }
        )
    random.shuffle(rows)
    seen: set[str] = set()
    out = []
    for row in rows:
        key = row["message_text_masked"]
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= n:
            break
    return out


async def _sample_llm_rejected(database_url: str, n: int) -> list[dict]:
    engine = create_async_engine(database_url)
    rows: list[dict] = []
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT chat_username, message_text_masked, llm_verdict
                    FROM llm_decisions
                    WHERE llm_verdict IN ('OFFER', 'OTHER')
                    ORDER BY id DESC
                    LIMIT 2000
                    """
                )
            )
            seen: set[str] = set()
            for chat, masked, verdict in result.all():
                key = masked or ""
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "source": "llm_rejected",
                        "chat_username": chat,
                        "message_text_masked": mask_message_text(masked or ""),
                        "llm_verdict": verdict,
                    }
                )
                if len(rows) >= n:
                    break
    finally:
        await engine.dispose()
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, help="Matching feedback batch id")
    parser.add_argument("--unmatched", type=int, default=50)
    parser.add_argument("--rejected", type=int, default=50)
    args = parser.parse_args()

    env = _read_env(PROJECT_ROOT / ".env")
    host = env.get("REDIS_HOST", "127.0.0.1")
    port = int(env.get("REDIS_PORT", "6379"))
    db = int(env.get("REDIS_DB", "0"))
    redis = Redis(host=host, port=port, db=db, decode_responses=True)

    pg_user = env.get("POSTGRES_USER", "leadhunter")
    pg_pass = env.get("POSTGRES_PASSWORD", "")
    pg_host = env.get("POSTGRES_HOST", "127.0.0.1")
    pg_port = env.get("POSTGRES_PORT", "5432")
    pg_db = env.get("POSTGRES_DB", "leadhunter")
    database_url = (
        f"postgresql+asyncpg://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    )

    try:
        unmatched = await _sample_unmatched(redis, args.unmatched)
    finally:
        await redis.aclose()

    rejected = await _sample_llm_rejected(database_url, args.rejected)
    rows = unmatched + rejected

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"recall_{args.batch}_{date.today().isoformat()}.md"
    lines = [
        f"# Recall sample — batch `{args.batch}`",
        "",
        "Fill manually: `missed_lead` (yes/no), `expected_segment`, `missed_at_layer` "
        "(keywords|reality|legacy_llm|v2|geo|other).",
        "",
        "| # | source | chat | masked_text | missed_lead | expected_segment | missed_at_layer |",
        "|---|--------|------|-------------|-------------|------------------|-----------------|",
    ]
    for i, row in enumerate(rows, 1):
        text_val = (row.get("message_text_masked") or "").replace("|", "/")
        lines.append(
            f"| {i} | {row.get('source')} | {row.get('chat_username')} | {text_val} |  |  |  |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())

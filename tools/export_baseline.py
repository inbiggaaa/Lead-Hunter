"""Baseline export for matching-quality eval (task 0.1 of fable_audit.md).

Read-only snapshot of production data — worker is NOT touched:
- llm_decisions (last N): rule/LLM verdicts with masked texts
- feedback (all): closed-matching snapshots + current labels
  (verdict taxonomy: correct/error/uncertain; legacy relevant/not_relevant
  may still appear until migration). SELECT * exports new columns including
  delivered/rule/reality segments, llm layer fields, keyword_only.
- stats:unmatched (last N from Redis): messages the classifier rejected

No PII columns should be present in feedback (masked text only).

Connects via localhost port bindings (127.0.0.1:5432 / 127.0.0.1:6379),
credentials read from .env. Output: JSONL files in docs/eval/.

Usage: venv/bin/python tools/export_baseline.py
"""

import asyncio
import json
from datetime import date
from pathlib import Path

import asyncpg
from redis.asyncio import Redis

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "docs" / "eval"
LIMIT = 500


def _read_env(path: Path) -> dict[str, str]:
    """Minimal .env parser — KEY=VALUE lines, no interpolation."""
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _jsonable(value):
    """Convert asyncpg row values to JSON-serializable types."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def export_table(conn, query: str, out_path: Path) -> int:
    rows = await conn.fetch(query)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            record = {k: _jsonable(v) for k, v in dict(row).items()}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(rows)


async def export_unmatched(redis: Redis, out_path: Path) -> int:
    entries = await redis.lrange("stats:unmatched", 0, LIMIT - 1)
    with out_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.strip() + "\n")  # entries are already JSON
    return len(entries)


async def main() -> None:
    env = _read_env(PROJECT_ROOT / ".env")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y-%m")

    conn = await asyncpg.connect(
        host="127.0.0.1",
        port=5432,
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        database=env["POSTGRES_DB"],
    )
    try:
        n_dec = await export_table(
            conn,
            f"SELECT * FROM llm_decisions ORDER BY id DESC LIMIT {LIMIT}",
            OUT_DIR / f"baseline_{stamp}.decisions.jsonl",
        )
        n_fb = await export_table(
            conn,
            "SELECT * FROM feedback ORDER BY id",
            OUT_DIR / f"baseline_{stamp}.feedback.jsonl",
        )
    finally:
        await conn.close()

    redis = Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
    try:
        n_unm = await export_unmatched(
            redis, OUT_DIR / f"baseline_{stamp}.unmatched.jsonl",
        )
    finally:
        await redis.aclose()

    print(f"decisions: {n_dec}, feedback: {n_fb}, unmatched: {n_unm}")
    print(f"written to {OUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())

"""Migration reversibility smoke for matching_feedback_v2."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _async_dsn() -> str:
    return (
        f"postgresql+asyncpg://{os.environ.get('POSTGRES_USER', 'lhtest')}:"
        f"{os.environ.get('POSTGRES_PASSWORD', 'lhtest')}@"
        f"{os.environ.get('POSTGRES_HOST', '127.0.0.1')}:"
        f"{os.environ.get('POSTGRES_PORT', '55432')}/"
        f"{os.environ.get('POSTGRES_DB', 'lhtest')}"
    )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            "POSTGRES_PORT": os.environ.get("POSTGRES_PORT", "55432"),
            "POSTGRES_USER": os.environ.get("POSTGRES_USER", "lhtest"),
            "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", "lhtest"),
            "POSTGRES_DB": os.environ.get("POSTGRES_DB", "lhtest"),
        }
    )
    return env


def _alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        check=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=_env(),
    )


@pytest_asyncio.fixture
async def migration_engine():
    """Isolated test DB only — never point this at production."""
    port = os.environ.get("POSTGRES_PORT", "55432")
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    if host == "db" or (port == "5432" and os.environ.get("ALLOW_FEEDBACK_MIGRATION_ON_DEFAULT_PORT") != "1"):
        pytest.skip("Refusing migration smoke against default/prod DB")

    engine = create_async_engine(_async_dsn())
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_matching_feedback_migration_upgrade_downgrade_upgrade(migration_engine):
    async with migration_engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE users (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE segments (
                    id BIGSERIAL PRIMARY KEY,
                    slug VARCHAR(50) UNIQUE NOT NULL
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE feedback (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chat_username VARCHAR(64) NOT NULL,
                    message_id INTEGER NOT NULL,
                    verdict VARCHAR(15) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(text("INSERT INTO users (telegram_id) VALUES (1)"))
        await conn.execute(
            text(
                "INSERT INTO feedback (user_id, chat_username, message_id, verdict) "
                "VALUES (1, 'c', 1, 'relevant'), (1, 'c', 2, 'not_relevant')"
            )
        )
        await conn.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        )
        await conn.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('segment_profile_audit01')"
            )
        )

    _alembic("upgrade", "head")

    async with migration_engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT verdict, reason_code, test_batch, public_token "
                "FROM feedback ORDER BY message_id"
            )
        )
        rows = result.mappings().all()
        assert rows[0]["verdict"] == "correct"
        assert rows[0]["reason_code"] is None
        assert rows[0]["test_batch"] == "legacy"
        assert rows[0]["public_token"]
        assert rows[1]["verdict"] == "error"
        assert rows[1]["reason_code"] == "other"

        await conn.execute(
            text(
                "INSERT INTO feedback ("
                "public_token, test_batch, user_id, chat_username, message_id, verdict"
                ") VALUES ('tokUnrated01', 'ru_matching_v1', 1, 'c', 3, NULL)"
            )
        )
        constraints = {
            r[0]
            for r in (
                await conn.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'feedback'::regclass"
                    )
                )
            )
        }
        assert "uq_feedback_public_token" in constraints
        assert "uq_feedback_batch_user_chat_msg" in constraints
        assert "ck_feedback_verdict" in constraints
        cols = {
            r[0]
            for r in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'feedback'"
                    )
                )
            )
        }
        assert "keyword_only" in cols

    _alembic("downgrade", "-1")  # keyword01 → matching_feedback_v2

    async with migration_engine.begin() as conn:
        cols = {
            r[0]
            for r in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'feedback'"
                    )
                )
            )
        }
        assert "keyword_only" not in cols
        assert "public_token" in cols

    _alembic("downgrade", "-1")  # matching_feedback_v2 → legacy

    async with migration_engine.begin() as conn:
        remaining = (
            await conn.execute(text("SELECT message_id, verdict FROM feedback ORDER BY 1"))
        ).all()
        assert remaining == [(1, "relevant"), (2, "not_relevant")]
        cols = {
            r[0]
            for r in (
                await conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'feedback'"
                    )
                )
            )
        }
        assert "public_token" not in cols
        assert "verdict" in cols

    _alembic("upgrade", "head")

    async with migration_engine.begin() as conn:
        head = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        assert head == "matching_feedback_keyword01"
        n = await conn.scalar(text("SELECT count(*) FROM feedback"))
        assert n == 2
        kw_default = await conn.scalar(
            text("SELECT keyword_only FROM feedback WHERE message_id = 1")
        )
        assert kw_default is False
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

"""Phase 5: supply-chain helpers (redis URL, non-root Dockerfile)."""

from pathlib import Path

from app.config import Settings


def test_redis_url_without_password(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "000000000:CI_DUMMY_TOKEN_NOT_REAL")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "1")
    monkeypatch.setenv("USERBOT_API_ID", "1")
    monkeypatch.setenv("USERBOT_API_HASH", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    s = Settings(_env_file=None)
    assert s.redis_url == "redis://redis:6379/0"


def test_redis_url_with_password_is_urlencoded(monkeypatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "000000000:CI_DUMMY_TOKEN_NOT_REAL")
    monkeypatch.setenv("OWNER_TELEGRAM_ID", "1")
    monkeypatch.setenv("USERBOT_API_ID", "1")
    monkeypatch.setenv("USERBOT_API_HASH", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("ADMIN_PASSWORD", "x")
    monkeypatch.setenv("REDIS_HOST", "redis")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss:word")
    s = Settings(_env_file=None)
    assert s.redis_url == "redis://:p%40ss%3Aword@redis:6379/0"


def test_dockerfile_runs_as_non_root() -> None:
    text = Path("Dockerfile").read_text()
    assert "USER app" in text
    assert "10001" in text
    assert "requirements.lock" in text


def test_compose_base_does_not_publish_db_redis() -> None:
    text = Path("docker-compose.yml").read_text()
    # Dev overlay publishes loopback ports; base file must not.
    assert "5432:5432" not in text
    assert "6379:6379" not in text
    assert "docker-compose.dev.yml"  # sanity: overlay exists
    assert Path("docker-compose.dev.yml").exists()
    assert Path("docker-compose.prod.yml").exists()
    assert Path("scripts/rollback.sh").exists()

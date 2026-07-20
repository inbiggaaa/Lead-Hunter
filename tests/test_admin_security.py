"""Regression tests for the admin security boundary."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, WebSocketDisconnect

from app.admin.api import auth, chat, require_auth

ROOT = Path(__file__).resolve().parents[1]


class _FakeRedisPipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self.redis = redis

    def incr(self, key: str) -> None:
        self.key = key

    def expire(self, key: str, duration: int) -> None:
        self.duration = duration

    async def execute(self) -> list[int]:
        attempts = self.redis.attempts.get(self.key, 0) + 1
        self.redis.attempts[self.key] = attempts
        return [attempts, 1]


class _FakeRedis:
    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}
        self.blocked: dict[str, int] = {}
        self.block_count: dict[str, int] = {}

    async def ttl(self, key: str) -> int:
        return self.blocked.get(key, -2)

    def pipeline(self) -> _FakeRedisPipeline:
        return _FakeRedisPipeline(self)

    async def incr(self, key: str) -> int:
        count = self.block_count.get(key, 0) + 1
        self.block_count[key] = count
        return count

    async def expire(self, key: str, duration: int) -> None:
        return None

    async def setex(self, key: str, duration: int, value: int) -> None:
        self.blocked[key] = duration

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.attempts.pop(key, None)
            self.block_count.pop(key, None)


class _RedisUnavailable:
    async def __call__(self) -> None:
        raise ConnectionError("Redis unavailable")


class _FakeWebSocket:
    def __init__(
        self,
        *,
        authenticated: bool,
        messages: list[dict[str, object]] | None = None,
    ) -> None:
        self.scope = {"session": {"authenticated": authenticated}}
        self.accept = AsyncMock()
        self.close = AsyncMock()
        self.send_json = AsyncMock()
        side_effects: list[object] = list(messages or [])
        side_effects.append(WebSocketDisconnect())
        self.receive_json = AsyncMock(side_effect=side_effects)


class _SessionContext:
    def __init__(self, session: Mock) -> None:
        self.session = session

    async def __aenter__(self) -> Mock:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


def _request(
    *,
    forwarded_for: str | None = None,
    peer_ip: str = "127.0.0.1",
) -> SimpleNamespace:
    headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=peer_ip),
        session={},
    )


async def _idle_listener(websocket: _FakeWebSocket) -> None:
    await asyncio.Event().wait()


def _bot() -> Mock:
    bot = Mock()
    bot.send_message = AsyncMock()
    bot.session.close = AsyncMock()
    return bot


def test_admin_compose_defaults_to_localhost_and_documents_override() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    env_example = (ROOT / ".env.example").read_text()

    assert (
        "${ADMIN_BIND_HOST:-127.0.0.1}:${ADMIN_PUBLIC_PORT:-17421}:8001"
        in compose
    )
    assert "ADMIN_BIND_HOST=127.0.0.1" in env_example
    assert "reverse proxy/TLS" in env_example


def test_get_ip_ignores_spoofed_forwarded_header_by_default(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "admin_trust_proxy_headers", False)

    assert auth._get_ip(_request(forwarded_for="203.0.113.10")) == "127.0.0.1"


def test_get_ip_trusts_forwarded_header_only_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "admin_trust_proxy_headers", True)

    assert auth._get_ip(_request(forwarded_for="203.0.113.10, 10.0.0.1")) == (
        "203.0.113.10"
    )


@pytest.mark.asyncio
async def test_require_auth_rejects_missing_session() -> None:
    with pytest.raises(HTTPException) as error:
        await require_auth(SimpleNamespace(session={}))

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_login_accepts_valid_password_and_uses_compare_digest(
    monkeypatch,
) -> None:
    redis = _FakeRedis()
    compare_digest = Mock(return_value=True)
    monkeypatch.setattr(auth, "get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(auth.secrets, "compare_digest", compare_digest)
    request = _request()

    response = await auth.login(request, auth.LoginRequest(password="valid"))

    assert response == {"ok": True}
    assert request.session == {"authenticated": True}
    compare_digest.assert_called_once_with("valid", auth.settings.admin_password)


@pytest.mark.asyncio
async def test_login_blocks_fifth_failed_attempt(monkeypatch) -> None:
    redis = _FakeRedis()
    monkeypatch.setattr(auth, "get_redis", AsyncMock(return_value=redis))
    request = _request()

    for _ in range(auth.MAX_ATTEMPTS - 1):
        with pytest.raises(HTTPException) as error:
            await auth.login(request, auth.LoginRequest(password="wrong"))
        assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        await auth.login(request, auth.LoginRequest(password="wrong"))

    assert error.value.status_code == 429
    assert redis.blocked["login_blocked:127.0.0.1"] == auth.BLOCK_DURATION
    assert request.session == {}


@pytest.mark.asyncio
async def test_login_returns_503_when_redis_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(auth, "get_redis", _RedisUnavailable())
    request = _request()

    with pytest.raises(HTTPException) as error:
        await auth.login(
            request,
            auth.LoginRequest(password=auth.settings.admin_password),
        )

    assert error.value.status_code == 503
    assert request.session == {}


@pytest.mark.asyncio
async def test_chat_websocket_rejects_missing_session() -> None:
    websocket = _FakeWebSocket(authenticated=False)

    await chat.chat_ws(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008)


@pytest.mark.asyncio
async def test_chat_websocket_accepts_authenticated_session(monkeypatch) -> None:
    websocket = _FakeWebSocket(authenticated=True)
    monkeypatch.setattr(chat, "_redis_listener", _idle_listener)
    monkeypatch.setattr(chat, "Bot", Mock(return_value=_bot()))

    await chat.chat_ws(websocket)

    websocket.accept.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_unknown_user_returns_error_without_persisting(monkeypatch) -> None:
    session = Mock()
    session.get = AsyncMock(return_value=None)
    session.add = Mock()
    session.commit = AsyncMock()
    websocket = _FakeWebSocket(
        authenticated=True,
        messages=[{"action": "send", "user_id": 999, "text": "hello"}],
    )
    monkeypatch.setattr(
        chat,
        "async_session_factory",
        Mock(return_value=_SessionContext(session)),
    )
    monkeypatch.setattr(chat, "_redis_listener", _idle_listener)
    monkeypatch.setattr(chat, "Bot", Mock(return_value=_bot()))

    await chat.chat_ws(websocket)

    websocket.send_json.assert_any_await(
        {"type": "error", "detail": "User not found"}
    )
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_resolves_telegram_id_and_reuses_bot(monkeypatch) -> None:
    user = SimpleNamespace(id=7, telegram_id=700)
    session = Mock()
    session.get = AsyncMock(return_value=user)
    session.add = Mock()
    session.commit = AsyncMock()
    websocket = _FakeWebSocket(
        authenticated=True,
        messages=[
            {
                "action": "send",
                "user_id": 7,
                "text": "<b>first</b>",
                "telegram_id": 999,
            },
            {"action": "send", "user_id": 7, "text": "second"},
        ],
    )
    bots: list[Mock] = []

    def create_bot(*, token: str) -> Mock:
        bot = _bot()
        bots.append(bot)
        return bot

    monkeypatch.setattr(
        chat,
        "async_session_factory",
        Mock(return_value=_SessionContext(session)),
    )
    monkeypatch.setattr(chat, "_redis_listener", _idle_listener)
    monkeypatch.setattr(chat, "Bot", create_bot)

    await chat.chat_ws(websocket)

    assert len(bots) == 1
    assert bots[0].send_message.await_args_list[0].args == (
        700,
        "💬 Поддержка:\n\n<b>first</b>",
    )
    assert bots[0].send_message.await_args_list[1].args == (
        700,
        "💬 Поддержка:\n\nsecond",
    )
    bots[0].session.close.assert_awaited_once()
    assert session.add.call_count == 2
    assert all(
        call.args[0].user_id == 7
        and call.args[0].direction == "outgoing"
        for call in session.add.call_args_list
    )

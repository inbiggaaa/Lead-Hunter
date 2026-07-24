"""Adaptive poll schedule policy and Redis persistence (pure + store)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)

SCHEDULE_KEY = "poll:schedule:v1"
SUMMARY_KEY = "poll:summary:v1"
ELIGIBILITY_GENERATION_KEY = "poll:eligibility:generation"

_CLASS_INTERVALS: dict[str, int] = {
    "A": 120,
    "B": 300,
    "C": 900,
    "D": 3600,
    "E": 21600,
}

_ERROR_BACKOFF_SECONDS = (3600, 6 * 3600, 24 * 3600, 7 * 86400)


class PollClass(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


@dataclass(frozen=True)
class PollOutcome:
    new_messages: int
    error_kind: str | None = None


@dataclass(frozen=True)
class PollScheduleState:
    poll_class: PollClass
    empty_streak: int
    error_streak: int = 0
    next_poll_at: int = 0
    last_message_at: int | None = None
    is_quarantined: bool = False


def interval_for(poll_class: PollClass) -> int:
    return _CLASS_INTERVALS[poll_class.value]


def next_schedule(
    previous: PollScheduleState | None,
    outcome: PollOutcome,
    now: int,
) -> PollScheduleState:
    if previous is None:
        if outcome.new_messages > 0:
            return PollScheduleState(
                poll_class=PollClass.A,
                empty_streak=0,
                error_streak=0,
                next_poll_at=now + interval_for(PollClass.A),
                last_message_at=now,
                is_quarantined=False,
            )
        return PollScheduleState(
            poll_class=PollClass.C,
            empty_streak=1,
            error_streak=0,
            next_poll_at=now + interval_for(PollClass.C),
            last_message_at=None,
            is_quarantined=False,
        )

    if outcome.error_kind:
        return _schedule_after_error(previous, outcome.error_kind, now)

    if outcome.new_messages > 0:
        return PollScheduleState(
            poll_class=PollClass.A,
            empty_streak=0,
            error_streak=0,
            next_poll_at=now + interval_for(PollClass.A),
            last_message_at=now,
            is_quarantined=False,
        )

    empty_streak = previous.empty_streak + 1
    poll_class = _class_after_empty(previous.poll_class, empty_streak)
    return PollScheduleState(
        poll_class=poll_class,
        empty_streak=empty_streak,
        error_streak=0,
        next_poll_at=now + interval_for(poll_class),
        last_message_at=previous.last_message_at,
        is_quarantined=False,
    )


def _class_after_empty(previous: PollClass, empty_streak: int) -> PollClass:
    # Thresholds are inclusive of the streak count after this empty poll.
    if previous is PollClass.A and empty_streak >= 3:
        return PollClass.B
    if previous in {PollClass.A, PollClass.B} and empty_streak >= 10:
        return PollClass.C
    if previous is PollClass.C and empty_streak >= 30:
        return PollClass.D
    if previous is PollClass.D and empty_streak >= 100:
        return PollClass.E
    if previous is PollClass.E:
        return PollClass.E
    # New C stays C until demotion threshold; never promote on empty.
    return previous


def _schedule_after_error(
    previous: PollScheduleState,
    error_kind: str,
    now: int,
) -> PollScheduleState:
    error_streak = previous.error_streak + 1
    if error_streak >= 5:
        return PollScheduleState(
            poll_class=previous.poll_class,
            empty_streak=previous.empty_streak,
            error_streak=error_streak,
            next_poll_at=now + _ERROR_BACKOFF_SECONDS[-1],
            last_message_at=previous.last_message_at,
            is_quarantined=True,
        )
    delay = _ERROR_BACKOFF_SECONDS[min(error_streak, len(_ERROR_BACKOFF_SECONDS)) - 1]
    return PollScheduleState(
        poll_class=previous.poll_class,
        empty_streak=previous.empty_streak,
        error_streak=error_streak,
        next_poll_at=now + delay,
        last_message_at=previous.last_message_at,
        is_quarantined=False,
    )


def state_to_json(state: PollScheduleState) -> str:
    return json.dumps(
        {
            "poll_class": state.poll_class.value,
            "empty_streak": state.empty_streak,
            "error_streak": state.error_streak,
            "next_poll_at": state.next_poll_at,
            "last_message_at": state.last_message_at,
            "is_quarantined": state.is_quarantined,
        },
        separators=(",", ":"),
    )


def state_from_json(raw: str) -> PollScheduleState:
    data = json.loads(raw)
    return PollScheduleState(
        poll_class=PollClass(data["poll_class"]),
        empty_streak=int(data.get("empty_streak", 0)),
        error_streak=int(data.get("error_streak", 0)),
        next_poll_at=int(data.get("next_poll_at", 0)),
        last_message_at=data.get("last_message_at"),
        is_quarantined=bool(data.get("is_quarantined", False)),
    )


def slice_size_for_power(base_slice: int, power_percent: int) -> int:
    if power_percent <= 0:
        return 0
    return max(1, int(base_slice * power_percent / 100))


def sort_due_chats(
    due: list[tuple[str, PollScheduleState]],
) -> list[tuple[str, PollScheduleState]]:
    priority = {PollClass.A: 0, PollClass.B: 1, PollClass.C: 2, PollClass.D: 3, PollClass.E: 4}

    def key(item: tuple[str, PollScheduleState]) -> tuple[int, int, str]:
        username, state = item
        return (state.next_poll_at, priority[state.poll_class], username)

    return sorted(due, key=key)


class PollScheduleStore:
    """Redis-backed schedule hash + compact summary."""

    def __init__(self, redis: Any):
        self._redis = redis
        self._memory: dict[str, PollScheduleState] = {}

    async def load(self) -> dict[str, PollScheduleState]:
        raw = await self._redis.hgetall(SCHEDULE_KEY)
        loaded: dict[str, PollScheduleState] = {}
        for username, value in (raw or {}).items():
            try:
                loaded[username] = state_from_json(value)
            except (KeyError, ValueError, json.JSONDecodeError):
                logger.warning("Invalid schedule entry for %s — skipped", username)
        self._memory = loaded
        return loaded

    def get(self, chat_username: str) -> PollScheduleState | None:
        return self._memory.get(chat_username)

    async def save(self, chat_username: str, state: PollScheduleState) -> None:
        self._memory[chat_username] = state
        await self._redis.hset(SCHEDULE_KEY, chat_username, state_to_json(state))

    async def remove(self, chat_username: str) -> None:
        self._memory.pop(chat_username, None)
        await self._redis.hdel(SCHEDULE_KEY, chat_username)

    async def save_summary(self, summary: dict[str, int | str]) -> None:
        mapping = {key: str(value) for key, value in summary.items()}
        if not mapping:
            return
        pipe = self._redis.pipeline()
        pipe.delete(SUMMARY_KEY)
        pipe.hset(SUMMARY_KEY, mapping=mapping)
        await pipe.execute()

    def due_chats(self, now: int, eligible: set[str]) -> list[tuple[str, PollScheduleState]]:
        due: list[tuple[str, PollScheduleState]] = []
        for username in eligible:
            state = self._memory.get(username)
            if state is None:
                state = PollScheduleState(
                    poll_class=PollClass.C,
                    empty_streak=0,
                    next_poll_at=now,
                )
            if state.is_quarantined:
                continue
            if state.next_poll_at <= now:
                due.append((username, state))
        return sort_due_chats(due)

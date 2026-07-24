"""Unit tests for adaptive poll schedule policy."""

from __future__ import annotations

import pytest

from app.userbot.poll_schedule import (
    PollClass,
    PollOutcome,
    PollScheduleState,
    next_schedule,
    slice_size_for_power,
)


def test_new_chat_starts_standard() -> None:
    state = next_schedule(None, PollOutcome(new_messages=0, error_kind=None), now=1000)
    assert state.poll_class is PollClass.C
    assert state.next_poll_at == 1000 + 900


def test_message_promotes_to_realtime() -> None:
    previous = PollScheduleState(
        poll_class=PollClass.E,
        empty_streak=100,
        error_streak=0,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=1, error_kind=None),
        now=1000,
    )
    assert state.poll_class is PollClass.A
    assert state.empty_streak == 0
    assert state.next_poll_at == 1120


@pytest.mark.parametrize(
    ("start_class", "empty_streak", "expected_class", "seconds"),
    [
        (PollClass.A, 3, PollClass.B, 300),
        (PollClass.B, 10, PollClass.C, 900),
        (PollClass.C, 30, PollClass.D, 3600),
        (PollClass.D, 100, PollClass.E, 21600),
    ],
)
def test_empty_streak_backoff(
    start_class: PollClass,
    empty_streak: int,
    expected_class: PollClass,
    seconds: int,
) -> None:
    previous = PollScheduleState(
        poll_class=start_class,
        empty_streak=empty_streak - 1,
        error_streak=0,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind=None),
        now=1000,
    )
    assert state.poll_class is expected_class
    assert state.empty_streak == empty_streak
    assert state.next_poll_at == 1000 + seconds


def test_empty_new_standard_chat_never_promotes_without_messages() -> None:
    previous = PollScheduleState(
        poll_class=PollClass.C,
        empty_streak=2,
        error_streak=0,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind=None),
        now=1000,
    )
    assert state.poll_class is PollClass.C
    assert state.next_poll_at == 1900


@pytest.mark.parametrize(
    ("error_streak_before", "delay"),
    [
        (0, 3600),
        (1, 6 * 3600),
        (2, 24 * 3600),
        (3, 7 * 86400),
    ],
)
def test_invalid_error_backoff(error_streak_before: int, delay: int) -> None:
    previous = PollScheduleState(
        poll_class=PollClass.C,
        empty_streak=0,
        error_streak=error_streak_before,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind="invalid"),
        now=1000,
    )
    assert state.error_streak == error_streak_before + 1
    assert state.next_poll_at == 1000 + delay
    assert state.is_quarantined is False


def test_fifth_error_quarantines() -> None:
    previous = PollScheduleState(
        poll_class=PollClass.C,
        empty_streak=0,
        error_streak=4,
        next_poll_at=0,
        last_message_at=None,
        is_quarantined=False,
    )
    state = next_schedule(
        previous,
        PollOutcome(new_messages=0, error_kind="private"),
        now=1000,
    )
    assert state.is_quarantined is True
    assert state.error_streak == 5


def test_slice_size_scales_with_power() -> None:
    assert slice_size_for_power(25, 100) == 25
    assert slice_size_for_power(25, 50) == 12
    assert slice_size_for_power(25, 10) == 2
    assert slice_size_for_power(25, 0) == 0

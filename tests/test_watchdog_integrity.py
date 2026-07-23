"""Behavioral regression checks for the host watchdog."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
WATCHDOG = ROOT / "scripts/watchdog.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _fake_commands(bin_dir: Path) -> None:
    _write_executable(
        bin_dir / "docker",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "inspect" ]]; then
    echo running
    exit 0
fi
key="${!#}"
if [[ "$*" == *"redis-cli GET"* ]]; then
    case "$key" in
        heartbeat:wall:userbot:1) date +%s ;;
        heartbeat:userbot:1) echo 1 ;;
        stats:worker:leader_rejected) echo "${LEADER_REJECTED:-0}" ;;
        stats:worker:leader_lost) echo 0 ;;
        *)
            state_file="$FAKE_REDIS_DIR/${key//:/_}"
            [[ -f "$state_file" ]] && tr -d '\\n' < "$state_file"
            ;;
    esac
    exit 0
fi
if [[ "$*" == *"redis-cli LLEN"* ]]; then
    echo 0
    exit 0
fi
if [[ "$*" == *"redis-cli SET"* ]]; then
    key="${@: -2:1}"
    value="${@: -1}"
    printf '%s' "$value" > "$FAKE_REDIS_DIR/${key//:/_}"
    echo OK
    exit 0
fi
exit 1
""",
    )
    _write_executable(
        bin_dir / "curl",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"api.telegram.org"* ]]; then
    printf '%s\\n' "$*" >> "$CURL_CAPTURE"
else
    printf '200'
fi
""",
    )
    _write_executable(
        bin_dir / "df",
        """#!/usr/bin/env bash
printf 'Filesystem 1024-blocks Used Available Capacity Mounted\\n'
printf '/dev/test 100 10 90 10%% /\\n'
""",
    )


def _macos_compatible_watchdog(tmp_path: Path) -> Path:
    script = WATCHDOG.read_text()
    associative_array = """declare -A EXPECTED=(
    [leadhunter-db-1]=""
    [leadhunter-redis-1]=""
    [leadhunter-bot-1]=""
    [leadhunter-worker-1]=""
    [leadhunter-admin-1]=""
)"""
    indexed_array = """EXPECTED=(
    leadhunter-db-1
    leadhunter-redis-1
    leadhunter-bot-1
    leadhunter-worker-1
    leadhunter-admin-1
)"""
    script = script.replace(associative_array, indexed_array)
    script = script.replace('"${!EXPECTED[@]}"', '"${EXPECTED[@]}"')
    test_script = tmp_path / "watchdog.sh"
    test_script.write_text(script)
    return test_script


def _run_watchdog(
    tmp_path: Path,
    *,
    admin_id: str,
    owner_id: str,
    leader_rejected: str = "5",
    cooldown: str = "0",
) -> list[str]:
    project_dir = tmp_path / "project"
    bin_dir = tmp_path / "bin"
    redis_dir = tmp_path / "redis"
    capture = tmp_path / "curl.log"
    project_dir.mkdir(exist_ok=True)
    bin_dir.mkdir(exist_ok=True)
    redis_dir.mkdir(exist_ok=True)
    _fake_commands(bin_dir)
    (project_dir / ".env").write_text(
        f"BOT_TOKEN=test-token\nADMIN_CHANNEL_ID={admin_id}\n"
        f"OWNER_TELEGRAM_ID={owner_id}\n"
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "PROJECT_DIR": str(project_dir),
        "ALERT_COOLDOWN": cooldown,
        "ALERT_COOLDOWN_FILE": str(tmp_path / "cooldown"),
        "FAKE_REDIS_DIR": str(redis_dir),
        "CURL_CAPTURE": str(capture),
        "LEADER_REJECTED": leader_rejected,
    }
    test_script = _macos_compatible_watchdog(tmp_path)
    subprocess.run(["bash", str(test_script)], check=True, env=env)
    if not capture.exists():
        return []
    return capture.read_text().splitlines()


def test_watchdog_prefers_admin_channel_over_owner(tmp_path: Path) -> None:
    calls = _run_watchdog(tmp_path, admin_id="-100123", owner_id="456")

    assert len(calls) == 1
    assert "chat_id=-100123" in calls[0]
    assert "chat_id=456" not in calls[0]


def test_watchdog_falls_back_to_owner(tmp_path: Path) -> None:
    calls = _run_watchdog(tmp_path, admin_id="", owner_id="456")

    assert len(calls) == 1
    assert "chat_id=456" in calls[0]


def test_watchdog_does_not_repeat_observed_leader_count(tmp_path: Path) -> None:
    first_calls = _run_watchdog(tmp_path, admin_id="-100123", owner_id="456")
    second_calls = _run_watchdog(tmp_path, admin_id="-100123", owner_id="456")

    assert len(first_calls) == 1
    assert len(second_calls) == 1


def test_watchdog_keeps_new_count_pending_during_cooldown(tmp_path: Path) -> None:
    _run_watchdog(tmp_path, admin_id="-100123", owner_id="456")
    suppressed_calls = _run_watchdog(
        tmp_path,
        admin_id="-100123",
        owner_id="456",
        leader_rejected="6",
        cooldown="1800",
    )
    delivered_calls = _run_watchdog(
        tmp_path,
        admin_id="-100123",
        owner_id="456",
        leader_rejected="6",
    )

    assert len(suppressed_calls) == 1
    assert len(delivered_calls) == 2

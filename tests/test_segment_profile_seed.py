"""Phase 2: approved RU segment LLM profile seed + validator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from seed.segment_llm_profiles_ru import load_profiles, load_profile_seed, profiles_json_path
from tools.validate_segment_profiles import (
    ProfileSeedError,
    _apply_guards,
    validate_seed_payload,
)

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "validate_segment_profiles.py"
FIXTURE = REPO / "tests" / "fixtures" / "segment_llm_profiles_ru.json"


def test_fixture_matches_seed_module():
    assert profiles_json_path().exists()
    assert FIXTURE.exists()
    seed = load_profile_seed()
    via_fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert seed["profiles"] == via_fixture["profiles"]


def test_seed_has_exactly_71_unique_slugs():
    profiles = load_profiles()
    slugs = [p["segment_slug"] for p in profiles]
    assert len(slugs) == 71
    assert len(set(slugs)) == 71


def test_each_profile_has_accept_reject_and_requires_llm():
    for row in load_profiles():
        assert row["locale"] == "ru"
        assert row["version"] == 1
        assert row["requires_llm"] is True
        assert row["target_lead"].strip()
        assert len(row["accept_examples"]) >= 1
        assert len(row["reject_examples"]) >= 1
        assert all(isinstance(x, str) and x.strip() for x in row["accept_examples"])
        assert all(isinstance(x, str) and x.strip() for x in row["reject_examples"])


def test_conflict_slugs_exist_in_seed():
    profiles = load_profiles()
    known = {p["segment_slug"] for p in profiles}
    for row in profiles:
        for c in row["conflict_slugs"]:
            assert c in known, f"{row['segment_slug']} → unknown conflict {c}"


def test_validate_seed_payload_ok():
    payload = load_profile_seed()
    assert validate_seed_payload(payload) == []


def test_validate_seed_payload_rejects_duplicate():
    payload = load_profile_seed()
    payload = json.loads(json.dumps(payload))
    payload["profiles"].append(payload["profiles"][0])
    errors = validate_seed_payload(payload)
    assert any("duplicate" in e for e in errors)


def test_validate_seed_payload_rejects_empty_accept():
    payload = load_profile_seed()
    payload = json.loads(json.dumps(payload))
    payload["profiles"][0]["accept_examples"] = []
    errors = validate_seed_payload(payload)
    assert any("accept_examples" in e for e in errors)


def test_apply_guards_block_without_env(monkeypatch):
    monkeypatch.delenv("LEADHUNTER_ALLOW_PROFILE_SEED", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    with pytest.raises(ProfileSeedError, match="LEADHUNTER_ALLOW_PROFILE_SEED"):
        _apply_guards(force_host=False)


def test_apply_guards_block_prod_host(monkeypatch):
    monkeypatch.setenv("LEADHUNTER_ALLOW_PROFILE_SEED", "1")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.delenv("LEADHUNTER_PROFILE_SEED_FORCE", raising=False)
    with pytest.raises(ProfileSeedError, match="denylisted"):
        _apply_guards(force_host=False)


def test_apply_guards_allow_localhost(monkeypatch):
    monkeypatch.setenv("LEADHUNTER_ALLOW_PROFILE_SEED", "1")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    _apply_guards(force_host=False)


def test_cli_validate_only_ok():
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--validate-only"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "71 profiles valid" in proc.stdout
    assert "0 missing segments" in proc.stdout
    assert "0 duplicate segment+locale pairs" in proc.stdout
    assert "0 unknown conflict slugs" in proc.stdout


def test_cli_apply_refuses_without_confirmation():
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO),
        "LEADHUNTER_ALLOW_PROFILE_SEED": "1",
        "POSTGRES_HOST": "127.0.0.1",
    }
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--apply"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "i-understand-this-writes-to-db" in proc.stderr

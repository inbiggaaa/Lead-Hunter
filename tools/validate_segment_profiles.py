#!/usr/bin/env python3
"""Validate / dry-run / apply / rollback segment LLM profiles.

Modes:
  --validate-only       structural + catalog checks (default if no mode)
  --dry-run             show insert/update plan against DB (no writes)
  --apply               upsert profiles (requires safety guards)
  --rollback-manifest   restore rows from a previous apply manifest

Safety:
  --apply refuses production-shaped hosts by default (POSTGRES_HOST=db).
  Requires LEADHUNTER_ALLOW_PROFILE_SEED=1 and --i-understand-this-writes-to-db.
  LEADHUNTER_PROFILE_SEED_FORCE=1 overrides the host denylist only (still needs
  the allow flag + confirmation switch). Never auto-runs on import.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seed.segment_llm_profiles_ru import load_profile_seed, profiles_json_path


PROD_HOST_DENYLIST = frozenset({"db", "postgres", "leadhunter-db-1"})


class ProfileSeedError(Exception):
    """Validation or apply guard failure."""


def _normalize_locale(locale: str) -> str:
    return (locale or "").strip().lower()


def validate_seed_payload(
    payload: dict[str, Any],
    *,
    active_slugs: set[str] | None = None,
) -> list[str]:
    """Return human-readable errors; empty list means OK."""
    errors: list[str] = []
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return ["profiles must be a list"]

    seen: set[tuple[str, str]] = set()
    slug_set: set[str] = set()
    for i, row in enumerate(profiles):
        prefix = f"profiles[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        slug = row.get("segment_slug")
        locale = _normalize_locale(str(row.get("locale", "ru")))
        if not isinstance(slug, str) or not slug.strip():
            errors.append(f"{prefix}: segment_slug required")
            continue
        slug = slug.strip()
        key = (slug, locale)
        if key in seen:
            errors.append(f"duplicate segment+locale: {slug}/{locale}")
        seen.add(key)
        slug_set.add(slug)

        target = (row.get("target_lead") or "").strip()
        if not target:
            errors.append(f"{prefix} ({slug}): empty target_lead")

        for field in ("accept_examples", "reject_examples", "conflict_slugs"):
            value = row.get(field)
            if not isinstance(value, list):
                errors.append(f"{prefix} ({slug}): {field} must be a list")
                continue
            if field != "conflict_slugs" and len(value) < 1:
                errors.append(f"{prefix} ({slug}): {field} needs ≥1 item")
            for j, item in enumerate(value):
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{prefix} ({slug}): {field}[{j}] invalid")

        if row.get("requires_llm") is not True:
            errors.append(f"{prefix} ({slug}): requires_llm must be true in v1")
        if row.get("version") != 1:
            errors.append(f"{prefix} ({slug}): version must be 1 in v1 seed")

    if active_slugs is not None:
        missing = sorted(active_slugs - slug_set)
        extra = sorted(slug_set - active_slugs)
        if missing:
            errors.append(f"missing segments ({len(missing)}): {', '.join(missing[:10])}")
        if extra:
            errors.append(f"unknown segments ({len(extra)}): {', '.join(extra[:10])}")
        # conflict slugs must exist in catalog
        for row in profiles:
            if not isinstance(row, dict):
                continue
            slug = row.get("segment_slug")
            for c in row.get("conflict_slugs") or []:
                if c not in active_slugs:
                    errors.append(f"{slug}: unknown conflict slug {c!r}")
    else:
        # self-contained: conflicts must be among seed slugs
        for row in profiles:
            if not isinstance(row, dict):
                continue
            slug = row.get("segment_slug")
            for c in row.get("conflict_slugs") or []:
                if c not in slug_set:
                    errors.append(f"{slug}: conflict slug {c!r} not in seed")

    if active_slugs is None and len(slug_set) != 71:
        errors.append(f"expected 71 profiles, got {len(slug_set)}")
    if active_slugs is not None and len(slug_set) != len(active_slugs):
        errors.append(
            f"profile count {len(slug_set)} != active segment count {len(active_slugs)}"
        )

    return errors


def _apply_guards(*, force_host: bool) -> None:
    if os.environ.get("LEADHUNTER_ALLOW_PROFILE_SEED") != "1":
        raise ProfileSeedError(
            "Refusing apply: set LEADHUNTER_ALLOW_PROFILE_SEED=1"
        )
    host = (os.environ.get("POSTGRES_HOST") or "").strip().lower()
    if host in PROD_HOST_DENYLIST and not force_host:
        raise ProfileSeedError(
            f"Refusing apply to denylisted host {host!r}. "
            "Use 127.0.0.1/localhost for isolated DB, or set "
            "LEADHUNTER_PROFILE_SEED_FORCE=1 only with owner approval."
        )


def _row_snapshot(profile: Any) -> dict[str, Any]:
    return {
        "id": profile.id,
        "segment_id": profile.segment_id,
        "locale": profile.locale,
        "target_lead": profile.target_lead,
        "accept_examples": list(profile.accept_examples or []),
        "reject_examples": list(profile.reject_examples or []),
        "conflict_slugs": list(profile.conflict_slugs or []),
        "requires_llm": bool(profile.requires_llm),
        "version": int(profile.version),
    }


async def _load_active_slugs() -> set[str]:
    from sqlalchemy import select
    from app.db.models import Segment
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        rows = await session.execute(
            select(Segment.slug).where(Segment.is_active.is_(True))
        )
        return {slug for (slug,) in rows.all()}


async def _plan_or_apply(
    payload: dict[str, Any],
    *,
    write: bool,
    manifest_path: Path | None,
) -> dict[str, Any]:
    from sqlalchemy import select
    from app.db import crud
    from app.db.models import Segment, SegmentLLMProfile
    from app.db.session import async_session_factory

    profiles = payload["profiles"]
    summary = {"insert": 0, "update": 0, "unchanged": 0, "rows": []}
    before: list[dict[str, Any]] = []

    async with async_session_factory() as session:
        seg_rows = (
            await session.execute(select(Segment).where(Segment.is_active.is_(True)))
        ).scalars().all()
        by_slug = {s.slug: s for s in seg_rows}

        for row in profiles:
            slug = row["segment_slug"]
            locale = _normalize_locale(row.get("locale", "ru"))
            seg = by_slug.get(slug)
            if seg is None:
                raise ProfileSeedError(f"active segment missing: {slug}")
            existing = await crud.get_segment_llm_profile(
                session, segment_id=seg.id, locale=locale
            )
            desired = {
                "target_lead": row["target_lead"].strip(),
                "accept_examples": [x.strip() for x in row["accept_examples"]],
                "reject_examples": [x.strip() for x in row["reject_examples"]],
                "conflict_slugs": [x.strip() for x in row["conflict_slugs"]],
                "requires_llm": True,
            }
            if existing is None:
                summary["insert"] += 1
                summary["rows"].append({"action": "insert", "slug": slug, "locale": locale})
                if write:
                    before.append(
                        {
                            "action": "insert",
                            "segment_slug": slug,
                            "locale": locale,
                            "previous": None,
                        }
                    )
                    await crud.create_segment_llm_profile(
                        session,
                        segment_id=seg.id,
                        locale=locale,
                        version=1,
                        **desired,
                    )
                continue

            same = (
                existing.target_lead == desired["target_lead"]
                and list(existing.accept_examples) == desired["accept_examples"]
                and list(existing.reject_examples) == desired["reject_examples"]
                and list(existing.conflict_slugs) == desired["conflict_slugs"]
                and bool(existing.requires_llm) is True
            )
            if same:
                summary["unchanged"] += 1
                summary["rows"].append({"action": "unchanged", "slug": slug, "locale": locale})
                continue

            summary["update"] += 1
            summary["rows"].append({"action": "update", "slug": slug, "locale": locale})
            if write:
                before.append(
                    {
                        "action": "update",
                        "segment_slug": slug,
                        "locale": locale,
                        "previous": _row_snapshot(existing),
                    }
                )
                await crud.update_segment_llm_profile(
                    session,
                    profile_id=existing.id,
                    target_lead=desired["target_lead"],
                    accept_examples=desired["accept_examples"],
                    reject_examples=desired["reject_examples"],
                    conflict_slugs=desired["conflict_slugs"],
                    requires_llm=True,
                )

        if write:
            await session.commit()
            if manifest_path is not None:
                manifest = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": str(profiles_json_path()),
                    "entries": before,
                }
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                summary["manifest"] = str(manifest_path)

    return summary


async def _rollback(manifest_path: Path) -> dict[str, Any]:
    from sqlalchemy import delete, select
    from app.db import crud
    from app.db.models import Segment, SegmentLLMProfile
    from app.db.session import async_session_factory

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries") or []
    restored = 0
    deleted = 0

    async with async_session_factory() as session:
        seg_rows = (await session.execute(select(Segment))).scalars().all()
        by_slug = {s.slug: s for s in seg_rows}

        for entry in reversed(entries):
            action = entry.get("action")
            slug = entry["segment_slug"]
            locale = _normalize_locale(entry.get("locale", "ru"))
            seg = by_slug.get(slug)
            if seg is None:
                raise ProfileSeedError(f"rollback: segment missing {slug}")
            current = await crud.get_segment_llm_profile(
                session, segment_id=seg.id, locale=locale
            )
            if action == "insert":
                if current is not None:
                    await session.execute(
                        delete(SegmentLLMProfile).where(SegmentLLMProfile.id == current.id)
                    )
                    deleted += 1
                continue
            if action == "update":
                prev = entry.get("previous")
                if prev is None:
                    raise ProfileSeedError(f"rollback: no previous for {slug}")
                if current is None:
                    await crud.create_segment_llm_profile(
                        session,
                        segment_id=seg.id,
                        locale=locale,
                        target_lead=prev["target_lead"],
                        accept_examples=prev["accept_examples"],
                        reject_examples=prev["reject_examples"],
                        conflict_slugs=prev["conflict_slugs"],
                        requires_llm=prev["requires_llm"],
                        version=prev["version"],
                    )
                else:
                    current.target_lead = prev["target_lead"]
                    current.accept_examples = prev["accept_examples"]
                    current.reject_examples = prev["reject_examples"]
                    current.conflict_slugs = prev["conflict_slugs"]
                    current.requires_llm = prev["requires_llm"]
                    current.version = prev["version"]
                restored += 1

        await session.commit()

    return {"restored": restored, "deleted_inserts": deleted}


def _print_validation(errors: list[str], profile_count: int) -> int:
    if errors:
        print(f"VALIDATION FAILED ({len(errors)} errors)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"{profile_count} profiles valid")
    print("0 missing segments")
    print("0 duplicate segment+locale pairs")
    print("0 unknown conflict slugs")
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else profiles_json_path()
    payload = load_profile_seed(path)
    profiles = payload["profiles"]

    active_slugs: set[str] | None = None
    if args.against_db:
        active_slugs = await _load_active_slugs()

    errors = validate_seed_payload(payload, active_slugs=active_slugs)
    if args.validate_only or (
        not args.dry_run and not args.apply and not args.rollback_manifest
    ):
        return _print_validation(errors, len(profiles))

    if errors:
        _print_validation(errors, len(profiles))
        return 1

    if args.rollback_manifest:
        if os.environ.get("LEADHUNTER_ALLOW_PROFILE_SEED") != "1":
            raise ProfileSeedError(
                "Refusing rollback: set LEADHUNTER_ALLOW_PROFILE_SEED=1"
            )
        if not args.i_understand_this_writes_to_db:
            raise ProfileSeedError(
                "Refusing rollback: pass --i-understand-this-writes-to-db"
            )
        result = await _rollback(Path(args.rollback_manifest))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.dry_run:
        summary = await _plan_or_apply(payload, write=False, manifest_path=None)
        print(
            f"dry-run: insert={summary['insert']} update={summary['update']} "
            f"unchanged={summary['unchanged']}"
        )
        return 0

    if args.apply:
        if not args.i_understand_this_writes_to_db:
            raise ProfileSeedError(
                "Refusing apply: pass --i-understand-this-writes-to-db"
            )
        force = os.environ.get("LEADHUNTER_PROFILE_SEED_FORCE") == "1"
        _apply_guards(force_host=force)
        manifest = Path(args.manifest) if args.manifest else Path(
            f"backups/profile_seed_manifest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        )
        summary = await _plan_or_apply(payload, write=True, manifest_path=manifest)
        print(
            f"applied: insert={summary['insert']} update={summary['update']} "
            f"unchanged={summary['unchanged']}"
        )
        print(f"rollback manifest: {summary['manifest']}")
        return 0

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Path to profiles JSON (default: seed/data/...)")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--rollback-manifest",
        metavar="PATH",
        help="Restore previous rows from apply manifest",
    )
    parser.add_argument(
        "--manifest",
        help="Where to write apply rollback manifest (default under backups/)",
    )
    parser.add_argument(
        "--against-db",
        action="store_true",
        help="Also require active segments from DB to match seed slugs",
    )
    parser.add_argument(
        "--i-understand-this-writes-to-db",
        action="store_true",
        help="Required confirmation switch for --apply / --rollback-manifest",
    )
    args = parser.parse_args()
    modes = sum(
        bool(x)
        for x in (args.validate_only, args.dry_run, args.apply, args.rollback_manifest)
    )
    if modes > 1:
        print("Choose only one mode", file=sys.stderr)
        return 2
    try:
        return asyncio.run(_async_main(args))
    except ProfileSeedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

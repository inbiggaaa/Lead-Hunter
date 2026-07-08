"""Focus on 21 priority countries — delete the rest.

Keep: Vietnam, Thailand, Indonesia, Philippines, India, China, Sri Lanka,
      UAE, Georgia, Spain, Italy, Montenegro, Cyprus, Northern Cyprus,
      Kazakhstan, Turkey, Egypt, Argentina, South Korea, Armenia, France.

Revision ID: focus_countries
Revises: add_watched_geo
Create Date: 2026-07-08
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "focus_countries"
down_revision: Union[str, None] = "add_watched_geo"
branch_labels: Union[dict[str, str], None] = None
depends_on: Union[list[str], None] = None

KEEP_SLUGS = [
    "vn", "th", "id", "ph", "in", "cn", "lk", "ae", "ge",
    "es", "it", "me", "cy", "north-cyprus", "kz", "tr",
    "eg", "ar", "южная-корея", "am", "fr",
]


def _build_in_clause(items: list[str]) -> str:
    """Build a safe IN clause from string literals (migration-only, controlled data)."""
    quoted = ", ".join(f"'{s}'" for s in items)
    return f"({quoted})"


def upgrade() -> None:
    conn = op.get_bind()
    slugs_clause = _build_in_clause(KEEP_SLUGS)

    # 1. Add Philippines (missing from DB)
    ph_exists = conn.execute(
        sa.text("SELECT 1 FROM countries WHERE slug = 'ph'")
    ).fetchone()
    if not ph_exists:
        conn.execute(
            sa.text("INSERT INTO countries (slug, name_ru, name_en, is_active) "
                    "VALUES ('ph', 'Филиппины', 'Philippines', true)")
        )

    # 2. Get keep_ids (now includes Philippines if just inserted)
    keep_rows = conn.execute(
        sa.text(f"SELECT id FROM countries WHERE slug IN {slugs_clause}")
    ).fetchall()
    keep_ids = {row[0] for row in keep_rows}
    keep_in = _build_in_clause([str(i) for i in keep_ids])

    print(f"  Keep: {len(keep_ids)} countries")

    # 3. Mark catalog channels in non-keep countries as ignored
    result = conn.execute(
        sa.text(
            "UPDATE catalog_channels SET is_ignored = true "
            "WHERE auto_matched_country_id IS NOT NULL "
            f"AND auto_matched_country_id NOT IN {keep_in}"
        )
    )
    print(f"  Marked {result.rowcount} catalog channels as ignored (non-focus countries)")

    # 4. Delete channel_cities for cities in non-keep countries
    result = conn.execute(
        sa.text(
            "DELETE FROM channel_cities WHERE city_id IN ("
            "  SELECT id FROM cities "
            f" WHERE country_id NOT IN {keep_in}"
            ")"
        )
    )
    print(f"  Deleted {result.rowcount} channel_cities rows")

    # 5. Delete subscription_cities for cities in non-keep countries
    result = conn.execute(
        sa.text(
            "DELETE FROM subscription_cities WHERE city_id IN ("
            "  SELECT id FROM cities "
            f" WHERE country_id NOT IN {keep_in}"
            ")"
        )
    )
    print(f"  Deleted {result.rowcount} subscription_cities rows")

    # 6. Delete cities in non-keep countries
    result = conn.execute(
        sa.text(f"DELETE FROM cities WHERE country_id NOT IN {keep_in}")
    )
    print(f"  Deleted {result.rowcount} cities in non-focus countries")

    # 7. Delete non-keep countries
    #    ON DELETE SET NULL: catalog_channels.auto_matched_country_id,
    #    watched_chats.country_id, discovered_chats.auto_matched_country_id
    #    ON DELETE CASCADE: user_subscriptions.country_id
    result = conn.execute(
        sa.text(f"DELETE FROM countries WHERE id NOT IN {keep_in}")
    )
    print(f"  Deleted {result.rowcount} countries (non-focus)")


def downgrade() -> None:
    """Cannot reverse — countries + cities lost permanently.
    Restore from backup (pg_dump) if needed.
    """
    raise NotImplementedError(
        "Downgrade not supported: deleted data is gone. "
        "Restore from pg_dump backup before migration date."
    )

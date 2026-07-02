"""dedup Samui + add UNIQUE(country_id, slug) on cities

Revision ID: 4afd135dc3f1
Revises: da0a81014466
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "4afd135dc3f1"
down_revision: Union[str, None] = "da0a81014466"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Remove duplicate channel_cities (same channels already under city 13)
    op.execute("DELETE FROM channel_cities WHERE city_id = 70")

    # 2. Migrate catalog_channels references
    op.execute("UPDATE catalog_channels SET auto_matched_city_id = 13 WHERE auto_matched_city_id = 70")

    # 3. Delete duplicate city
    op.execute("DELETE FROM cities WHERE id = 70")

    # 4. Add UNIQUE(country_id, slug)
    op.create_unique_constraint("uq_cities_country_slug", "cities", ["country_id", "slug"])


def downgrade() -> None:
    op.drop_constraint("uq_cities_country_slug", "cities", type_="unique")

    op.execute(
        "INSERT INTO cities (id, slug, name_ru, name_en, country_id, is_active) "
        "VALUES (70, 'samui', 'Самуи', 'Samui', 3, true)"
    )
    # Note: channel_cities (24 rows deleted) and catalog_channels (2 rows moved)
    # cannot be restored — city record is re-created but FK data is permanently merged.

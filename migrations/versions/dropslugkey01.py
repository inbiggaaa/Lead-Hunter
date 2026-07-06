"""drop global cities_slug_key (keep per-country uq_cities_country_slug)

Revision ID: dropslugkey01
Revises: manrev01
Create Date: 2026-07-05
"""
from alembic import op

revision = 'dropslugkey01'
down_revision = 'manrev01'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('cities_slug_key', 'cities', type_='unique')


def downgrade():
    op.create_unique_constraint('cities_slug_key', 'cities', ['slug'])

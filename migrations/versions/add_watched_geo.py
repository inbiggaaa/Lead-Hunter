"""add country_id + city_id to watched_chats for geo-tiered private groups"""
from alembic import op
import sqlalchemy as sa

revision = "add_watched_geo"
down_revision = "matchscore01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("watched_chats",
        sa.Column("country_id", sa.BigInteger(), nullable=True))
    op.add_column("watched_chats",
        sa.Column("city_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_watched_chats_country", "watched_chats", "countries",
        ["country_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key(
        "fk_watched_chats_city", "watched_chats", "cities",
        ["city_id"], ["id"], ondelete="SET NULL")


def downgrade():
    op.drop_constraint("fk_watched_chats_city", "watched_chats", type_="foreignkey")
    op.drop_constraint("fk_watched_chats_country", "watched_chats", type_="foreignkey")
    op.drop_column("watched_chats", "city_id")
    op.drop_column("watched_chats", "country_id")

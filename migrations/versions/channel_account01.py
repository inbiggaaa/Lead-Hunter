"""catalog_channels.userbot_account_id — привязка канала к аккаунту (13.07.2026).

Приватные -100…-чаты доступны только аккаунту-участнику (сеть TravelAsk —
@mill_sofi, account_id=2). _distribute обязан отдавать такой канал только
своему аккаунту: чужой не отрезолвит entity (ValueError на каждом цикле).
NULL = канал публичный, распределяется round-robin как раньше.
"""

from alembic import op
import sqlalchemy as sa

revision = "channel_account01"
down_revision = "quarantine01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_channels",
        sa.Column("userbot_account_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("catalog_channels", "userbot_account_id")

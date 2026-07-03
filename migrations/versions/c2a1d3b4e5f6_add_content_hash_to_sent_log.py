"""add content_hash to sent_log for 24h content-based dedup

Revision ID: c2a1d3b4e5f6
Revises: b11187f388a9
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c2a1d3b4e5f6"
down_revision: Union[str, None] = "b11187f388a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sent_log", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index(
        "idx_sent_log_content_dedup",
        "sent_log",
        ["user_id", "content_hash", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_sent_log_content_dedup", table_name="sent_log")
    op.drop_column("sent_log", "content_hash")

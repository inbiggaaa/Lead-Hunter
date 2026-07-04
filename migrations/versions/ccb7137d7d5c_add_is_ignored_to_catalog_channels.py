"""add is_ignored to catalog_channels

Revision ID: ccb7137d7d5c
Revises: c2a1d3b4e5f6
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ccb7137d7d5c"
down_revision: Union[str, None] = "c2a1d3b4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "catalog_channels",
        sa.Column("is_ignored", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("catalog_channels", "is_ignored")

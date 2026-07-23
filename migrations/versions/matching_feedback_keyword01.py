"""Persist keyword_only flag on closed matching feedback snapshots.

Revision ID: matching_feedback_keyword01
Revises: matching_feedback_v2
"""

from alembic import op
import sqlalchemy as sa


revision = "matching_feedback_keyword01"
down_revision = "matching_feedback_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "feedback",
        sa.Column(
            "keyword_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("feedback", "keyword_only")

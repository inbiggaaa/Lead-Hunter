"""Lifecycle anchor and one-time winback offers (U8/U9)."""

from alembic import op
import sqlalchemy as sa

revision = "winback_u89"
down_revision = "user_digest01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("free_lifecycle_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "winback_offers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("winback_offers")
    op.drop_column("users", "free_lifecycle_at")

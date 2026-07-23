"""segment_llm_profile drafts + admin audit log (Phase 10).

Adds draft_payload on published profiles and an append-only audit table.
Worker runtime still reads only published columns (not draft).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "segment_profile_audit01"
down_revision = "segment_profiles01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "segment_llm_profiles",
        sa.Column("draft_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_table(
        "segment_llm_profile_audits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=False),
        sa.Column("segment_slug", sa.String(length=50), nullable=False),
        sa.Column("admin_user", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("before_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["segment_llm_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_segment_llm_profile_audits_profile",
        "segment_llm_profile_audits",
        ["profile_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_segment_llm_profile_audits_profile",
        table_name="segment_llm_profile_audits",
    )
    op.drop_table("segment_llm_profile_audits")
    op.drop_column("segment_llm_profiles", "draft_payload")

"""segment_llm_profiles — compact per-segment LLM guidance (Phase 1).

Empty after upgrade: no automatic seed/apply. Keywords stay in segment_keywords.
Does not duplicate segments.lead_direction or segment titles.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "segment_profiles01"
down_revision = "stability_referral01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "segment_llm_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("segment_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "locale",
            sa.String(length=10),
            nullable=False,
            server_default="ru",
        ),
        sa.Column("target_lead", sa.Text(), nullable=False),
        sa.Column("accept_examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reject_examples", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("conflict_slugs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "requires_llm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["segments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "segment_id",
            "locale",
            name="uq_segment_llm_profiles_segment_locale",
        ),
    )


def downgrade() -> None:
    op.drop_table("segment_llm_profiles")

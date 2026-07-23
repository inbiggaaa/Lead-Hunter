"""Expand feedback into closed matching snapshot + current label.

Downgrade deletes unrated experimental rows (verdict IS NULL) before restoring
the legacy NOT NULL verdict column — unrated closed-test items cannot map to
legacy relevant/not_relevant.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "matching_feedback_v2"
down_revision = "segment_profile_audit01"
branch_labels = None
depends_on = None

_REASON_VALUES = (
    "wrong_category",
    "provider_offer",
    "job_vacancy",
    "job_search",
    "social_request",
    "discussion_news",
    "wrong_geography",
    "duplicate",
    "other",
)


def upgrade() -> None:
    op.add_column(
        "feedback",
        sa.Column("public_token", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column("test_batch", sa.String(length=64), nullable=True),
    )
    op.add_column("feedback", sa.Column("message_hash", sa.String(length=64), nullable=True))
    op.add_column("feedback", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("feedback", sa.Column("message_text_masked", sa.Text(), nullable=True))
    op.add_column(
        "feedback",
        sa.Column("delivered_segments", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column("rule_segments", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column("reality_segments", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column("legacy_llm_verdict", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column("legacy_llm_segments", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column("feedback", sa.Column("v2_intent", sa.String(length=40), nullable=True))
    op.add_column(
        "feedback",
        sa.Column("v2_segment_verdicts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("feedback", sa.Column("model_name", sa.String(length=64), nullable=True))
    op.add_column("feedback", sa.Column("prompt_version", sa.Integer(), nullable=True))
    op.add_column("feedback", sa.Column("schema_version", sa.Integer(), nullable=True))
    op.add_column(
        "feedback",
        sa.Column("profile_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("feedback", sa.Column("reason_code", sa.String(length=32), nullable=True))
    op.add_column(
        "feedback",
        sa.Column("confirmed_segments", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column("feedback", sa.Column("expected_segment_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "feedback",
        sa.Column("expected_segment_slug", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column(
            "expected_segment_missing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "feedback",
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "feedback",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Deterministic legacy backfill before tightening constraints.
    op.execute(
        """
        UPDATE feedback
        SET
            public_token = COALESCE(
                public_token,
                substr(md5(random()::text || id::text || clock_timestamp()::text), 1, 12)
            ),
            test_batch = COALESCE(test_batch, 'legacy'),
            reason_code = CASE
                WHEN verdict = 'not_relevant' THEN 'other'
                ELSE reason_code
            END,
            confirmed_segments = CASE
                WHEN verdict = 'relevant' THEN COALESCE(delivered_segments, ARRAY[]::varchar[])
                ELSE confirmed_segments
            END,
            rated_at = COALESCE(rated_at, created_at),
            verdict = CASE
                WHEN verdict = 'relevant' THEN 'correct'
                WHEN verdict = 'not_relevant' THEN 'error'
                ELSE verdict
            END
        """
    )

    # Any remaining NULL tokens (empty table) get placeholders for NOT NULL.
    op.execute(
        """
        UPDATE feedback
        SET public_token = substr(md5(id::text || 'seed'), 1, 12)
        WHERE public_token IS NULL
        """
    )
    op.execute(
        """
        UPDATE feedback
        SET test_batch = 'legacy'
        WHERE test_batch IS NULL
        """
    )

    op.alter_column("feedback", "public_token", nullable=False)
    op.alter_column("feedback", "test_batch", nullable=False)
    op.alter_column("feedback", "verdict", existing_type=sa.String(length=15), nullable=True)

    op.create_foreign_key(
        "fk_feedback_expected_segment",
        "feedback",
        "segments",
        ["expected_segment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_feedback_public_token", "feedback", ["public_token"])
    op.create_unique_constraint(
        "uq_feedback_batch_user_chat_msg",
        "feedback",
        ["test_batch", "user_id", "chat_username", "message_id"],
    )
    op.create_check_constraint(
        "ck_feedback_verdict",
        "feedback",
        "verdict IS NULL OR verdict IN ('correct', 'error', 'uncertain')",
    )
    reason_list = ", ".join(f"'{r}'" for r in _REASON_VALUES)
    op.create_check_constraint(
        "ck_feedback_reason_code",
        "feedback",
        f"reason_code IS NULL OR reason_code IN ({reason_list})",
    )
    op.create_check_constraint(
        "ck_feedback_verdict_reason",
        "feedback",
        "("
        "  (verdict = 'error' AND reason_code IS NOT NULL)"
        "  OR (verdict IS DISTINCT FROM 'error' AND reason_code IS NULL)"
        "  OR verdict IS NULL"
        ")",
    )
    op.create_check_constraint(
        "ck_feedback_expected_conflict",
        "feedback",
        "NOT (expected_segment_id IS NOT NULL AND expected_segment_missing)",
    )


def downgrade() -> None:
    # Unrated closed-test rows cannot map to legacy NOT NULL verdict.
    op.execute("DELETE FROM feedback WHERE verdict IS NULL")

    op.drop_constraint("ck_feedback_expected_conflict", "feedback", type_="check")
    op.drop_constraint("ck_feedback_verdict_reason", "feedback", type_="check")
    op.drop_constraint("ck_feedback_reason_code", "feedback", type_="check")
    op.drop_constraint("ck_feedback_verdict", "feedback", type_="check")
    op.drop_constraint("uq_feedback_batch_user_chat_msg", "feedback", type_="unique")
    op.drop_constraint("uq_feedback_public_token", "feedback", type_="unique")
    op.drop_constraint("fk_feedback_expected_segment", "feedback", type_="foreignkey")

    op.execute(
        """
        UPDATE feedback
        SET verdict = CASE
            WHEN verdict = 'correct' THEN 'relevant'
            ELSE 'not_relevant'
        END
        """
    )
    op.alter_column("feedback", "verdict", existing_type=sa.String(length=15), nullable=False)

    for col in (
        "updated_at",
        "rated_at",
        "expected_segment_missing",
        "expected_segment_slug",
        "expected_segment_id",
        "confirmed_segments",
        "reason_code",
        "profile_versions",
        "schema_version",
        "prompt_version",
        "model_name",
        "v2_segment_verdicts",
        "v2_intent",
        "legacy_llm_segments",
        "legacy_llm_verdict",
        "reality_segments",
        "rule_segments",
        "delivered_segments",
        "message_text_masked",
        "content_hash",
        "message_hash",
        "test_batch",
        "public_token",
    ):
        op.drop_column("feedback", col)

"""segment_llm_profile drafts + admin audit log (Phase 10).

Adds draft_payload on published profiles and an append-only audit table.
Worker runtime still reads only published columns (not draft).

Upgrade/downgrade are IF EXISTS / IF NOT EXISTS so CI head-reversibility
smoke (Base.metadata.create_all → stamp head → downgrade -1 → upgrade head)
does not fail when the model already created the same objects.
"""

from alembic import op


revision = "segment_profile_audit01"
down_revision = "segment_profiles01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent for CI smoke (create_all may already have applied model shape).
    op.execute(
        "ALTER TABLE segment_llm_profiles "
        "ADD COLUMN IF NOT EXISTS draft_payload JSONB"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS segment_llm_profile_audits (
            id BIGSERIAL PRIMARY KEY,
            profile_id BIGINT NOT NULL REFERENCES segment_llm_profiles(id) ON DELETE CASCADE,
            segment_id BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
            segment_slug VARCHAR(50) NOT NULL,
            admin_user VARCHAR(64) NOT NULL,
            action VARCHAR(20) NOT NULL,
            before_json JSONB,
            after_json JSONB,
            reason TEXT NOT NULL DEFAULT '',
            version_after INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_segment_llm_profile_audits_profile "
        "ON segment_llm_profile_audits (profile_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_segment_llm_profile_audits_profile")
    op.execute("DROP TABLE IF EXISTS segment_llm_profile_audits")
    op.execute(
        "ALTER TABLE segment_llm_profiles DROP COLUMN IF EXISTS draft_payload"
    )

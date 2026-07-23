"""Move referral share code to users; make invitee edges immutable.

Revision ID: stability_referral01
Revises: u94_lifecycle_optout
"""

from alembic import op
import sqlalchemy as sa


revision = "stability_referral01"
down_revision = "u94_lifecycle_optout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(length=20), nullable=True),
    )

    # Backfill one stable code per referrer from the oldest referral row.
    op.execute(
        """
        UPDATE users AS u
        SET referral_code = src.ref_code
        FROM (
            SELECT DISTINCT ON (referrer_id) referrer_id, ref_code
            FROM referrals
            ORDER BY referrer_id, id
        ) AS src
        WHERE u.id = src.referrer_id
          AND u.referral_code IS NULL
        """
    )

    # Self-placeholder rows (referrer == invitee) are no longer needed.
    op.execute("DELETE FROM referrals WHERE referral_id = referrer_id")

    op.create_unique_constraint(
        "uq_users_referral_code", "users", ["referral_code"],
    )

    # Drop global uniqueness on edge.ref_code so many invitees can share a code.
    op.execute("ALTER TABLE referrals DROP CONSTRAINT IF EXISTS referrals_ref_code_key")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_referrals_referrer_paid_month "
        "ON referrals (referrer_id, activated_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_referrals_referrer_paid_month")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'referrals_ref_code_key'
            ) THEN
                ALTER TABLE referrals
                    ADD CONSTRAINT referrals_ref_code_key UNIQUE (ref_code);
            END IF;
        END $$;
        """
    )

    # Restore one self-placeholder per user that still has a code and no edges.
    op.execute(
        """
        INSERT INTO referrals (referrer_id, referral_id, ref_code, status)
        SELECT u.id, u.id, u.referral_code, 'active'
        FROM users u
        WHERE u.referral_code IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM referrals r WHERE r.referrer_id = u.id
          )
        """
    )

    # create_all may name the unique constraint users_referral_code_key;
    # the migration itself uses uq_users_referral_code.
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS uq_users_referral_code")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_referral_code_key")
    op.drop_column("users", "referral_code")

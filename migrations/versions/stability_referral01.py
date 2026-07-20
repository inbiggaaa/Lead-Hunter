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
    op.drop_constraint("referrals_ref_code_key", "referrals", type_="unique")
    op.create_index(
        "idx_referrals_referrer_paid_month",
        "referrals",
        ["referrer_id", "activated_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_referrals_referrer_paid_month", table_name="referrals")
    op.create_unique_constraint(
        "referrals_ref_code_key", "referrals", ["ref_code"],
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

    op.drop_constraint("uq_users_referral_code", "users", type_="unique")
    op.drop_column("users", "referral_code")

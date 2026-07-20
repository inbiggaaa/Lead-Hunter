"""U9.4 — extend periodic_prefs msg_type with lifecycle_marketing opt-out.

Legacy calendar types (weekly_digest / niche_growth / monthly_summary) stay valid
for historical rows; active marketing is Free EOD reports + day-30 winback.
"""

from alembic import op


revision = "u94_lifecycle_optout"
down_revision = "pay_idempotency01"
branch_labels = None
depends_on = None

_OLD = (
    "msg_type IN ('weekly_digest', 'niche_growth', 'monthly_summary')"
)
_NEW = (
    "msg_type IN ('weekly_digest', 'niche_growth', 'monthly_summary', "
    "'lifecycle_marketing')"
)


def upgrade() -> None:
    op.drop_constraint("ck_periodic_prefs_msg_type", "periodic_prefs", type_="check")
    op.create_check_constraint(
        "ck_periodic_prefs_msg_type",
        "periodic_prefs",
        _NEW,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM periodic_prefs WHERE msg_type = 'lifecycle_marketing'"
    )
    op.drop_constraint("ck_periodic_prefs_msg_type", "periodic_prefs", type_="check")
    op.create_check_constraint(
        "ck_periodic_prefs_msg_type",
        "periodic_prefs",
        _OLD,
    )

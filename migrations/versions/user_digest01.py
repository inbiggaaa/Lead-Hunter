"""users.digest_mode — режим доставки уведомлений (T5.3, 13.07.2026).

instant (дефолт) / hourly / daily2. Митигация шума при безлимите уведомлений (#81):
фича комфорта, доступна всем. Срочные (🔥) всегда доставляются мгновенно.
"""

from alembic import op
import sqlalchemy as sa

revision = "user_digest01"
down_revision = "sentlog_meta01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("digest_mode", sa.String(10), nullable=False, server_default="instant"),
    )


def downgrade() -> None:
    op.drop_column("users", "digest_mode")

"""subscriptions.provider_charge_id — идемпотентность оплаты (P0).

UNIQUE partial index WHERE NOT NULL: повторный Stars/CryptoBot charge
не создаёт вторую подписку и не продлевает тариф заново.
"""

from alembic import op
import sqlalchemy as sa


revision = "pay_idempotency01"
down_revision = "winback_u89"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("provider_charge_id", sa.String(128), nullable=True),
    )
    # Postgres UNIQUE allows multiple NULLs — legacy rows stay NULL.
    op.create_unique_constraint(
        "uq_subscriptions_provider_charge_id",
        "subscriptions",
        ["provider_charge_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_subscriptions_provider_charge_id",
        "subscriptions",
        type_="unique",
    )
    op.drop_column("subscriptions", "provider_charge_id")

"""segments.is_quarantined — карантин сегмента (A3 fable_core_plan, 12.07.2026).

Карантинный сегмент продолжает матчиться и логироваться в llm_decisions
(датасет копится), но НЕ диспатчится пользователям. Включается руками
в админке (/catalog → Направления) для сегментов-паразитов с precision ~0%
(massage 0/8, design 0/16 по фидбеку на 12.07). Автоматики нет — оценок
слишком мало для авто-решений.
"""

from alembic import op
import sqlalchemy as sa

revision = "quarantine01"
down_revision = "lead_direction01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "segments",
        sa.Column(
            "is_quarantined",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("segments", "is_quarantined")

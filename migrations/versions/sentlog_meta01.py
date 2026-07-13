"""sent_log: метаданные для CSV-экспорта Бизнеса (T5.2, 13.07.2026).

Владелец выбрал экспорт БЕЗ полного текста заявки (приватность/место). Добавляем
chat_username / sender / segment / message_id — nullable, заполняются с даты деплоя
(старые строки остаются NULL, экспорт покрывает данные с момента накатки).
"""

from alembic import op
import sqlalchemy as sa

revision = "sentlog_meta01"
down_revision = "channel_account01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sent_log", sa.Column("chat_username", sa.String(64), nullable=True))
    op.add_column("sent_log", sa.Column("sender", sa.String(64), nullable=True))
    op.add_column("sent_log", sa.Column("segment", sa.Text(), nullable=True))
    op.add_column("sent_log", sa.Column("message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("sent_log", "message_id")
    op.drop_column("sent_log", "segment")
    op.drop_column("sent_log", "sender")
    op.drop_column("sent_log", "chat_username")

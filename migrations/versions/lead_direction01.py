"""segments.lead_direction — направление лида из БД вместо хардкода (B4).

Кто является ЛИДОМ в каждом сегменте и как выглядит его сообщение:

  'demand' — лид ИЩЕТ услугу («ищу мастера», «нужен сантехник»).
             Pass 3 классификатора активен, LLM-промпт обычный.
  'buy'    — лид ПОКУПАЕТ/СНИМАЕТ и пишет спрос с бюджетом/контактом
             («куплю авто до 10к$», «сниму квартиру, бюджет, тел»).
             Pass 3 пропускается (цена/телефон у лида — норма),
             LLM-промпт обычный («куплю» = DEMAND).
  'supply' — лид ПРОДАЁТ, его сообщение выглядит как оффер
             («продам байк, 3 млн, документы»). Pass 3 пропускается,
             DEMAND/OFFER в LLM-промпте инвертируется.

Фактические направления (сверено с demand-keywords в БД):
  moto-purchase / car-purchase → 'supply'
      (наш клиент — покупатель; keywords «продам байк», «продам авто»)
  moto-sale / car-sale         → 'buy'
      (наш клиент — продавец; keywords «куплю байк», «куплю авто»)
  housing-buy                  → 'buy'
      (keywords «куплю квартиру» — лид-покупатель; ДО этой миграции был
       ошибочно в инвертированном блоке LLM-промпта)
  housing-rent                 → 'buy'
      (keywords «сниму квартиру» — лид-арендатор)
  все остальные                → 'demand'

Заменяет: константу PURCHASE_SEGMENTS в classifier.py (Pass 3 skip =
lead_direction IN ('buy','supply')) и хардкод «PURCHASE SEGMENTS» в
LLM-промпте (инверсия = lead_direction = 'supply').
"""

from alembic import op
import sqlalchemy as sa

revision = "lead_direction01"
down_revision = "cat_hierarchy_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "segments",
        sa.Column(
            "lead_direction", sa.String(10),
            nullable=False, server_default="demand",
        ),
    )
    op.execute(
        "UPDATE segments SET lead_direction = 'supply' "
        "WHERE slug IN ('moto-purchase', 'car-purchase')"
    )
    op.execute(
        "UPDATE segments SET lead_direction = 'buy' "
        "WHERE slug IN ('moto-sale', 'car-sale', 'housing-buy', 'housing-rent')"
    )


def downgrade() -> None:
    op.drop_column("segments", "lead_direction")

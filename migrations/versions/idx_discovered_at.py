"""index on catalog_channels.discovered_at (filter Новые)"""
from alembic import op
# revision идентификаторы:
revision = "idx_disc_at01"
down_revision = "ccb7137d7d5c"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_catalog_channels_discovered_at",
                    "catalog_channels", ["discovered_at"])

def downgrade():
    op.drop_index("ix_catalog_channels_discovered_at",
                  table_name="catalog_channels")

"""add manually_reviewed to catalog_channels"""
from alembic import op
import sqlalchemy as sa
revision = "manrev01"
down_revision = "idx_disc_at01"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("catalog_channels",
        sa.Column("manually_reviewed", sa.Boolean(),
                  nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("catalog_channels", "manually_reviewed")

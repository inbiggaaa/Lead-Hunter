"""add match_score + needs_review to catalog_channels"""
from alembic import op
import sqlalchemy as sa

revision = "matchscore01"
down_revision = "dropslugkey01"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("catalog_channels",
        sa.Column("match_score", sa.Float(), nullable=True))
    op.add_column("catalog_channels",
        sa.Column("needs_review", sa.Boolean(), nullable=False,
                  server_default=sa.false()))

def downgrade():
    op.drop_column("catalog_channels", "needs_review")
    op.drop_column("catalog_channels", "match_score")

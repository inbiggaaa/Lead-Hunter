"""add llm_decisions and feedback tables

Revision ID: b11187f388a9
Revises: 4afd135dc3f1
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b11187f388a9"
down_revision: Union[str, None] = "4afd135dc3f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chat_username", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("message_text_masked", sa.Text(), nullable=False),
        sa.Column("rule_segments", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("llm_verdict", sa.String(length=20), nullable=False),
        sa.Column("llm_segments", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("llm_reason", sa.Text(), nullable=True),
        sa.Column("certainty", sa.String(length=10), nullable=True),
        sa.Column("llm_mode", sa.String(length=10), server_default="shadow"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_llm_decisions_created", "llm_decisions", ["created_at"])
    op.create_index("idx_llm_decisions_chat_msg", "llm_decisions", ["chat_username", "message_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_username", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(length=15), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feedback_chat_msg", "feedback", ["chat_username", "message_id"])


def downgrade() -> None:
    op.drop_index("idx_feedback_chat_msg", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("idx_llm_decisions_chat_msg", table_name="llm_decisions")
    op.drop_index("idx_llm_decisions_created", table_name="llm_decisions")
    op.drop_table("llm_decisions")

"""Add conversation_threads and thread_messages tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-02

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_threads",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("plugin_slug", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("conversation_threads_user_id", "conversation_threads", ["user_id"])

    op.create_table(
        "thread_messages",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "thread_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("conversation_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "query_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("queries.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('user','assistant')", name="thread_messages_role_check"),
    )
    op.create_index("thread_messages_thread_id", "thread_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("thread_messages_thread_id", table_name="thread_messages")
    op.drop_table("thread_messages")
    op.drop_index("conversation_threads_user_id", table_name="conversation_threads")
    op.drop_table("conversation_threads")

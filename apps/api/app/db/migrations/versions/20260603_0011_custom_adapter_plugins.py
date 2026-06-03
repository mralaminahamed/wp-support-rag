"""Add adapter_plugins table and drop sources_source_type_check constraint.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260603_0011"
down_revision: str | None = "20260603_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop sources_source_type_check constraint (source_type values are now
    #    open-ended — adapters may register arbitrary source types).
    op.drop_constraint("sources_source_type_check", "sources", type_="check")

    # 2. Create adapter_plugins table.
    op.create_table(
        "adapter_plugins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("entry_point", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("handles", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "config_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'loaded'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "installed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("slug", name="adapter_plugins_slug_key"),
        sa.CheckConstraint(
            "source IN ('builtin', 'entrypoint', 'file')",
            name="adapter_plugins_source_check",
        ),
        sa.CheckConstraint(
            "status IN ('loaded', 'error', 'disabled')",
            name="adapter_plugins_status_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("adapter_plugins")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support',"
        "'webpage','rest_endpoint')",
    )

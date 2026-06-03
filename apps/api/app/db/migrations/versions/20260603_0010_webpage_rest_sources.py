"""Add Source.name, drop unique(plugin_id, source_type), add unique(plugin_id, name), extend source_type check.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add name column (temporarily nullable so we can backfill).
    op.add_column("sources", sa.Column("name", sa.Text(), nullable=True))

    # 2. Backfill: name = source_type for all existing rows.
    op.execute("UPDATE sources SET name = source_type")

    # 3. Make name NOT NULL now that all rows have a value.
    op.alter_column("sources", "name", nullable=False)

    # 4. Drop the old unique constraint.
    op.drop_constraint("sources_plugin_id_source_type_key", "sources", type_="unique")

    # 5. Add new unique constraint on (plugin_id, name).
    op.create_unique_constraint("sources_plugin_id_name_key", "sources", ["plugin_id", "name"])

    # 6. Drop old source_type CHECK constraint and add updated one.
    op.drop_constraint("sources_source_type_check", "sources", type_="check")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support',"
        "'webpage','rest_endpoint')",
    )


def downgrade() -> None:
    # Reverse order.
    op.drop_constraint("sources_source_type_check", "sources", type_="check")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support')",
    )
    op.drop_constraint("sources_plugin_id_name_key", "sources", type_="unique")
    op.create_unique_constraint(
        "sources_plugin_id_source_type_key", "sources", ["plugin_id", "source_type"]
    )
    op.drop_column("sources", "name")

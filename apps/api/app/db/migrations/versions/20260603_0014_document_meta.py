"""Add meta JSONB column to documents for adapter-specific metadata.

Revision ID: 20260603_0014
Revises: 20260603_0013
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260603_0014"
down_revision = "20260603_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("meta", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "meta")

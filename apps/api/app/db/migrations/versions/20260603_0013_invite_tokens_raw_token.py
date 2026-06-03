"""Add raw_token to invite_tokens for copy-link without regeneration.

Revision ID: 20260603_0013
Revises: 20260603_0012
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invite_tokens",
        sa.Column("raw_token", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invite_tokens", "raw_token")

"""Add 'queued' to ingestion_runs status check constraint.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-02

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260602_0006"
down_revision: str | None = "20260602_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ingestion_runs_status_check", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ingestion_runs_status_check",
        "ingestion_runs",
        sa.text("status IN ('queued','running','succeeded','failed')"),
    )


def downgrade() -> None:
    op.drop_constraint("ingestion_runs_status_check", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "ingestion_runs_status_check",
        "ingestion_runs",
        sa.text("status IN ('running','succeeded','failed')"),
    )

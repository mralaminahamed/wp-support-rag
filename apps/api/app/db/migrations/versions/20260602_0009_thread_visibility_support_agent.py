"""Add threads:read_all permission to super_admin/admin; rename editor role to support_agent.

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260602_0009"
down_revision: str | None = "20260602_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Grant threads:read_all to super_admin and admin roles.
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission)
        VALUES
            ('55a5b674-c9d3-5e1a-8f2b-1a2b3c4d5e6f', 'threads:read_all'),
            ('66b6c785-dae4-6f2b-9a3c-2b3c4d5e6f7a', 'threads:read_all')
        ON CONFLICT DO NOTHING
        """
    )

    # 2. Rename non-system editor role to support_agent.
    op.execute(
        """
        UPDATE roles
        SET name = 'support_agent',
            description = 'Manage plugins and trigger ingestion. No settings, metrics, or user access.'
        WHERE name = 'editor'
          AND is_system = false
        """
    )


def downgrade() -> None:
    # 1. Rename support_agent back to editor.
    op.execute(
        """
        UPDATE roles
        SET name = 'editor',
            description = 'Manage plugins and trigger ingestion. No settings, metrics, or user access.'
        WHERE name = 'support_agent'
          AND is_system = false
        """
    )

    # 2. Remove threads:read_all from super_admin and admin roles.
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission = 'threads:read_all'
          AND role_id IN (
              '55a5b674-c9d3-5e1a-8f2b-1a2b3c4d5e6f',
              '66b6c785-dae4-6f2b-9a3c-2b3c4d5e6f7a'
          )
        """
    )

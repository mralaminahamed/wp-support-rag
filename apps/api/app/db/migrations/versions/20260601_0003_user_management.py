"""User management: users, roles, permissions, refresh/invite tokens.

Creates six new tables, adds the `pgcrypto` extension for gen_random_uuid(),
and seeds three system roles with their permission sets.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-01

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUPER_ADMIN_PERMS = (
    "plugins:read",
    "plugins:write",
    "ingestion:trigger",
    "metrics:read",
    "settings:read",
    "settings:write",
    "users:read",
    "users:write",
    "users:invite",
)
_ADMIN_PERMS = tuple(p for p in _SUPER_ADMIN_PERMS if p != "users:write")
_VIEWER_PERMS = ("plugins:read", "metrics:read", "settings:read", "users:read")

# Stable UUIDs for system roles — consistent across environments.
_SUPER_ADMIN_ID = "55a5b674-c9d3-5e1a-8f2b-1a2b3c4d5e6f"
_ADMIN_ID = "66b6c785-dae4-6f2b-9a3c-2b3c4d5e6f7a"
_VIEWER_ID = "77c7d896-ebf5-7a3c-ab4d-3c4d5e6f7a8b"


def upgrade() -> None:
    """Create auth tables and seed system roles."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "roles",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("permission", sa.Text(), nullable=False, primary_key=True),
    )

    op.create_table(
        "user_roles",
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "role_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
    )

    op.create_table(
        "user_permissions",
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("permission", sa.Text(), nullable=False, primary_key=True),
        sa.Column("granted", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "refresh_tokens",
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
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "invite_tokens",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "role_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )

    conn = op.get_bind()

    roles = [
        (_SUPER_ADMIN_ID, "super_admin", "Full access to every resource.", True, _SUPER_ADMIN_PERMS),
        (_ADMIN_ID, "admin", "Full access except user account management.", True, _ADMIN_PERMS),
        (_VIEWER_ID, "viewer", "Read-only access across all resources.", True, _VIEWER_PERMS),
    ]

    for role_id, name, description, is_system, perms in roles:
        conn.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, is_system) "
                "VALUES (:id, :name, :desc, :sys) ON CONFLICT DO NOTHING"
            ),
            {"id": role_id, "name": name, "desc": description, "sys": is_system},
        )
        for perm in perms:
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission) "
                    "VALUES (:rid, :perm) ON CONFLICT DO NOTHING"
                ),
                {"rid": role_id, "perm": perm},
            )


def downgrade() -> None:
    """Drop all auth tables."""
    op.drop_table("invite_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("user_permissions")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("users")

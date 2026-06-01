# Author: Al Amin Ahamed
"""Seed one custom ``editor`` role.

System roles (super_admin, admin, viewer) are seeded by the Alembic migration
and are never touched here. This seeder only manages the non-system ``editor``
role so it is safe to truncate independently.

Default credentials are for development only — DO NOT USE IN PRODUCTION.

editor permissions: plugins:read, plugins:write, ingestion:trigger
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role, RolePermission
from app.seeders.base import Seeder

_EDITOR_ROLE = {
    "name": "editor",
    "description": "Manage plugins and trigger ingestion. No settings, metrics, or user access.",
    "permissions": ["plugins:read", "plugins:write", "ingestion:trigger"],
}


class RolesSeeder(Seeder):
    name = "roles"
    depends_on = []
    truncate_sql = [
        # Only remove non-system roles — never touch super_admin/admin/viewer.
        "DELETE FROM roles WHERE is_system = false",
    ]

    async def run(self, db: AsyncSession, *, count: int) -> int:  # noqa: ARG002
        inserted = 0
        spec = _EDITOR_ROLE
        existing = (
            await db.execute(select(Role).where(Role.name == spec["name"]))
        ).scalar_one_or_none()
        if existing is not None:
            return 0

        role = Role(
            name=spec["name"],
            description=spec["description"],
            is_system=False,
        )
        db.add(role)
        await db.flush()

        for perm in spec["permissions"]:
            db.add(RolePermission(role_id=role.id, permission=perm))
        await db.flush()
        inserted += 1
        return inserted

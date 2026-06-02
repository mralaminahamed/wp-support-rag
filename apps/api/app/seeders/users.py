# Author: Al Amin Ahamed
"""Seed dev users — superadmin and admin only.

Idempotent: skips users whose email already exists.

Default credentials (DO NOT USE IN PRODUCTION):
    superadmin@dev.local  / DevPass123!  — super_admin (all permissions)
    admin@dev.local       / DevPass123!  — admin       (no users:write)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.db.models import Role, User, UserRole
from app.seeders.base import Seeder

_FIXTURES: list[dict] = [
    {"email": "superadmin@dev.local", "password": "DevPass123!", "role": "super_admin", "active": True},
    {"email": "admin@dev.local",      "password": "DevPass123!", "role": "admin",       "active": True},
]

_SEEDED_EMAILS = {f["email"] for f in _FIXTURES}


class UsersSeeder(Seeder):
    name = "users"
    depends_on = ["roles"]
    truncate_sql = [
        "DELETE FROM users WHERE email = ANY(ARRAY[{}])".format(
            ", ".join(f"'{e}'" for e in sorted(_SEEDED_EMAILS))
        ),
    ]

    async def run(self, db: AsyncSession, *, count: int) -> int:  # noqa: ARG002
        inserted = 0
        for fx in _FIXTURES:
            existing = (
                await db.execute(select(User).where(User.email == fx["email"]))
            ).scalar_one_or_none()
            if existing is not None:
                continue

            role = (
                await db.execute(select(Role).where(Role.name == fx["role"]))
            ).scalar_one_or_none()
            if role is None:
                raise RuntimeError(
                    f"role {fx['role']!r} not found — run roles seeder first"
                )

            user = User(
                email=fx["email"],
                password_hash=hash_password(fx["password"]),
                is_active=fx["active"],
            )
            db.add(user)
            await db.flush()
            db.add(UserRole(user_id=user.id, role_id=role.id))
            inserted += 1

        await db.flush()
        return inserted

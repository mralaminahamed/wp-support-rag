# Author: Al Amin Ahamed
"""Plugin seeder — intentionally empty.

Plugins are registered through the setup wizard or the admin UI.
No placeholder data is seeded so the system starts in a clean, realistic state.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.seeders.base import Seeder


class PluginsSeeder(Seeder):
    name = "plugins"
    depends_on = []
    truncate_sql = []

    async def run(self, db: AsyncSession, *, count: int) -> int:  # noqa: ARG002
        return 0

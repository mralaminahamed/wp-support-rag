# Author: Al Amin Ahamed
"""Base seeder class for sample data generation.

Pattern: Laravel-style seeders. Each seeder is idempotent — re-running on
populated tables uses skip-if-exists semantics. Use ``--fresh`` to truncate
first.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


class Seeder(ABC):
    """Abstract base for table seeders.

    Subclasses declare:
    - name: short identifier matching the CLI --table flag
    - depends_on: list of seeder names that must run first
    - truncate_sql: SQL statements executed when --fresh is passed
    """

    name: str = ""
    depends_on: list[str] = []
    truncate_sql: list[str] = []

    @abstractmethod
    async def run(self, db: AsyncSession, *, count: int) -> int:
        """Seed the table. Return number of rows inserted."""

    async def truncate(self, db: AsyncSession) -> None:
        from sqlalchemy import text as _text  # noqa: PLC0415

        for stmt in self.truncate_sql:
            await db.execute(_text(stmt))

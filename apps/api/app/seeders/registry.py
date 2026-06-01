# Author: Al Amin Ahamed
"""Seeder registry — ordered by dependency."""
from __future__ import annotations

from app.seeders.base import Seeder
from app.seeders.plugins import PluginsSeeder
from app.seeders.roles import RolesSeeder
from app.seeders.users import UsersSeeder

# Order matters: earlier seeders are dependencies of later ones.
SEEDERS: list[type[Seeder]] = [
    RolesSeeder,
    UsersSeeder,
    PluginsSeeder,
]

SEEDERS_BY_NAME: dict[str, type[Seeder]] = {s.name: s for s in SEEDERS}

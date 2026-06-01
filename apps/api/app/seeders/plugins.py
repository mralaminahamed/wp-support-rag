# Author: Al Amin Ahamed
"""Seed sample plugins with sources for development.

Creates 3 sample plugins that cover typical source-type combinations so the
admin Plugins page and ingestion flows have realistic data to work with.
Idempotent: skips plugins whose slug already exists.

Seeded plugins
--------------
| Slug                    | Sources                                          |
|-------------------------|--------------------------------------------------|
| hello-dolly             | wporg_faq, wporg_changelog                       |
| woocommerce             | wporg_faq, wporg_changelog, github_readme        |
| contact-form-7          | wporg_faq, wporg_changelog, wporg_support        |
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plugin
from app.ingestion.registry import add_source, create_plugin
from app.seeders.base import Seeder

_PLUGINS: list[dict] = [
    {
        "slug": "hello-dolly",
        "name": "Hello Dolly",
        "wporg_slug": "hello-dolly",
        "github_repo": None,
        "sources": [
            {"source_type": "wporg_faq"},
            {"source_type": "wporg_changelog"},
        ],
    },
    {
        "slug": "woocommerce",
        "name": "WooCommerce",
        "wporg_slug": "woocommerce",
        "github_repo": "woocommerce/woocommerce",
        "sources": [
            {"source_type": "wporg_faq"},
            {"source_type": "wporg_changelog"},
            {"source_type": "github_readme"},
        ],
    },
    {
        "slug": "contact-form-7",
        "name": "Contact Form 7",
        "wporg_slug": "contact-form-7",
        "github_repo": None,
        "sources": [
            {"source_type": "wporg_faq"},
            {"source_type": "wporg_changelog"},
            {"source_type": "wporg_support"},
        ],
    },
]

_SEEDED_SLUGS = {p["slug"] for p in _PLUGINS}


class PluginsSeeder(Seeder):
    name = "plugins"
    depends_on = []
    truncate_sql = [
        "DELETE FROM plugins WHERE slug = ANY(ARRAY[{}])".format(
            ", ".join(f"'{s}'" for s in sorted(_SEEDED_SLUGS))
        ),
    ]

    async def run(self, db: AsyncSession, *, count: int) -> int:  # noqa: ARG002
        inserted = 0
        for spec in _PLUGINS:
            existing = (
                await db.execute(select(Plugin).where(Plugin.slug == spec["slug"]))
            ).scalar_one_or_none()
            if existing is not None:
                continue

            plugin = await create_plugin(
                db,
                slug=spec["slug"],
                name=spec["name"],
                wporg_slug=spec.get("wporg_slug"),
                github_repo=spec.get("github_repo"),
            )
            for src in spec.get("sources", []):
                await add_source(
                    db,
                    plugin_id=plugin.id,
                    source_type=src["source_type"],
                )
            inserted += 1

        await db.flush()
        return inserted

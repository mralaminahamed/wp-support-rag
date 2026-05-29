"""Plugin and source registry.

Async CRUD for plugins and their typed sources (FR-PM-1/2/3) plus a declarative
loader that registers a plugin and its full source set from a YAML or TOML file
(FR-PM-5). The loader is idempotent: re-loading the same config updates the
plugin and reconciles its sources rather than duplicating them.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SOURCE_TYPES, Plugin, Source

SourceType = Literal[
    "github_readme",
    "github_changelog",
    "github_docs",
    "github_issues",
    "wporg_faq",
    "wporg_changelog",
    "wporg_support",
]


class SourceSpec(BaseModel):
    """Declarative specification of a single source within a plugin config.

    Attributes:
        source_type: The typed source kind.
        enabled: Whether ingestion runs for this source (FR-PM-3).
        config: Adapter-specific configuration (labels, paths, state, ...).
    """

    source_type: SourceType
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PluginSpec(BaseModel):
    """Declarative specification of a plugin and its sources (FR-PM-5).

    Attributes:
        slug: Unique plugin slug.
        name: Display name.
        wporg_slug: Optional WordPress.org slug.
        github_repo: Optional ``owner/name`` GitHub repository.
        sources: The sources to attach to the plugin.
    """

    slug: str
    name: str
    wporg_slug: str | None = None
    github_repo: str | None = None
    sources: list[SourceSpec] = Field(default_factory=list)


async def get_plugin_by_slug(session: AsyncSession, slug: str) -> Plugin | None:
    """Return the plugin with the given slug, if it exists.

    Args:
        session: Active async session.
        slug: Plugin slug to look up.

    Returns:
        Plugin | None: The matching plugin, or ``None``.
    """
    result = await session.execute(select(Plugin).where(Plugin.slug == slug))
    return result.scalar_one_or_none()


async def list_plugins(session: AsyncSession) -> list[Plugin]:
    """Return all registered plugins ordered by slug.

    Args:
        session: Active async session.

    Returns:
        list[Plugin]: All plugins.
    """
    result = await session.execute(select(Plugin).order_by(Plugin.slug))
    return list(result.scalars().all())


async def create_plugin(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    wporg_slug: str | None = None,
    github_repo: str | None = None,
) -> Plugin:
    """Register a new plugin (FR-PM-1).

    Args:
        session: Active async session.
        slug: Unique plugin slug.
        name: Display name.
        wporg_slug: Optional WordPress.org slug.
        github_repo: Optional ``owner/name`` GitHub repository.

    Returns:
        Plugin: The persisted plugin.
    """
    plugin = Plugin(slug=slug, name=name, wporg_slug=wporg_slug, github_repo=github_repo)
    session.add(plugin)
    await session.flush()
    return plugin


async def add_source(
    session: AsyncSession,
    *,
    plugin_id: Any,
    source_type: str,
    config: dict[str, Any] | None = None,
    enabled: bool = True,
) -> Source:
    """Attach a typed source to a plugin (FR-PM-2).

    Args:
        session: Active async session.
        plugin_id: Owning plugin id.
        source_type: One of the supported source types.
        config: Adapter-specific configuration.
        enabled: Whether the source is enabled.

    Returns:
        Source: The persisted source.

    Raises:
        ValueError: If ``source_type`` is not a supported type.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source_type: {source_type}")
    source = Source(
        plugin_id=plugin_id,
        source_type=source_type,
        config=config or {},
        enabled=enabled,
    )
    session.add(source)
    await session.flush()
    return source


async def list_sources(
    session: AsyncSession, plugin_id: Any, *, enabled_only: bool = False
) -> list[Source]:
    """List a plugin's sources.

    Args:
        session: Active async session.
        plugin_id: Owning plugin id.
        enabled_only: When ``True``, return only enabled sources.

    Returns:
        list[Source]: The plugin's sources ordered by source type.
    """
    stmt = select(Source).where(Source.plugin_id == plugin_id)
    if enabled_only:
        stmt = stmt.where(Source.enabled.is_(True))
    result = await session.execute(stmt.order_by(Source.source_type))
    return list(result.scalars().all())


async def set_source_enabled(session: AsyncSession, source_id: Any, enabled: bool) -> None:
    """Enable or disable a source without deleting it (FR-PM-3).

    Args:
        session: Active async session.
        source_id: The source to update.
        enabled: New enabled state.

    Raises:
        ValueError: If the source does not exist.
    """
    source = await session.get(Source, source_id)
    if source is None:
        raise ValueError(f"source not found: {source_id!r}")
    source.enabled = enabled
    await session.flush()


def parse_plugin_config(path: Path) -> PluginSpec:
    """Parse a YAML or TOML plugin configuration file.

    Args:
        path: Path to a ``.yaml``/``.yml`` or ``.toml`` config file.

    Returns:
        PluginSpec: The validated specification.

    Raises:
        ValueError: If the file extension is unsupported.
    """
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif suffix == ".toml":
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"unsupported config format: {suffix}")
    return PluginSpec.model_validate(data)


async def load_plugin_spec(session: AsyncSession, spec: PluginSpec) -> Plugin:
    """Register or reconcile a plugin and its sources from a spec (FR-PM-5).

    Idempotent: an existing plugin (matched by slug) is updated in place and its
    sources reconciled by source type, so re-loading never creates duplicates.

    Args:
        session: Active async session.
        spec: The plugin specification.

    Returns:
        Plugin: The persisted plugin with its sources attached.
    """
    plugin = await get_plugin_by_slug(session, spec.slug)
    if plugin is None:
        plugin = await create_plugin(
            session,
            slug=spec.slug,
            name=spec.name,
            wporg_slug=spec.wporg_slug,
            github_repo=spec.github_repo,
        )
    else:
        plugin.name = spec.name
        plugin.wporg_slug = spec.wporg_slug
        plugin.github_repo = spec.github_repo

    existing = {source.source_type: source for source in await list_sources(session, plugin.id)}
    for source_spec in spec.sources:
        current = existing.get(source_spec.source_type)
        if current is None:
            await add_source(
                session,
                plugin_id=plugin.id,
                source_type=source_spec.source_type,
                config=source_spec.config,
                enabled=source_spec.enabled,
            )
        else:
            current.config = source_spec.config
            current.enabled = source_spec.enabled
    await session.flush()
    return plugin


async def load_plugin_config(session: AsyncSession, path: Path) -> Plugin:
    """Load a plugin and its sources from a config file (FR-PM-5).

    Args:
        session: Active async session.
        path: Path to the YAML or TOML config file.

    Returns:
        Plugin: The persisted plugin.
    """
    return await load_plugin_spec(session, parse_plugin_config(path))

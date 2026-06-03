"""AdapterRegistry — discovers, loads, and manages source-type adapters.

Built-in adapters (GitHub, WordPress.org, Webpage, REST Endpoint) are loaded
first; then third-party adapters installed as Python entry-points; then
file-dropped adapters from ``settings.custom_adapters_dir``. Each loaded
adapter is upserted into the ``adapter_plugins`` DB table so the admin UI can
surface its status.

Conflict rules:
- A custom adapter claiming a type already owned by a built-in gets
  ``status='error'`` in the DB row but the built-in remains active.
- A custom adapter claiming a type already owned by another custom adapter:
  first-loaded wins, second gets ``status='error'``.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import get_settings
from app.db.models import AdapterPlugin
from app.ingestion.adapters.github import GitHubAdapter
from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter
from app.ingestion.adapters.webpage import WebpageAdapter
from app.ingestion.adapters.wporg import WporgAdapter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Multi-instance rules per source type
# ---------------------------------------------------------------------------

_SINGLE_INSTANCE_TYPES: frozenset[str] = frozenset(
    {
        "github_readme",
        "github_changelog",
        "github_docs",
        "github_issues",
        "wporg_faq",
        "wporg_changelog",
        "wporg_support",
    }
)
"""Source types where only one source per plugin makes sense (multi_instance=False)."""

# ---------------------------------------------------------------------------
# Built-in adapter metadata
# ---------------------------------------------------------------------------

_BUILTINS: list[tuple[type[Any], str, str]] = [
    (GitHubAdapter, "builtin.github", "GitHub"),
    (WporgAdapter, "builtin.wporg", "WordPress.org"),
    (WebpageAdapter, "builtin.webpage", "Webpage"),
    (RestEndpointAdapter, "builtin.rest_endpoint", "REST Endpoint"),
]
"""(adapter_class, slug, display_name) for each built-in adapter."""


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


class AdapterTypeInfo(BaseModel):
    """Metadata about a single registered source type.

    Attributes:
        source_type: The source-type string (e.g. ``"github_readme"``).
        display_name: Human-readable name shown in the admin UI.
        adapter_slug: Unique slug of the owning adapter (e.g. ``"builtin.github"``).
        config_schema: JSON Schema describing the adapter configuration.
        is_builtin: True when the adapter ships with the application.
        multi_instance: True when multiple sources of this type per plugin are allowed.
    """

    source_type: str
    display_name: str
    adapter_slug: str
    config_schema: dict[str, Any]
    is_builtin: bool
    multi_instance: bool


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------


class AdapterRegistry:
    """In-process mapping from source type strings to adapter instances.

    Built by :func:`build_registry` on startup; available at runtime via
    :func:`get_registry`.
    """

    def __init__(
        self,
        type_map: dict[str, Any],
        type_info: list[AdapterTypeInfo],
    ) -> None:
        """Construct a registry from pre-built mappings.

        Args:
            type_map: Maps source-type string -> adapter instance.
            type_info: Ordered list of ``AdapterTypeInfo`` for every active type.
        """
        self._type_map: dict[str, Any] = type_map
        self._type_info: list[AdapterTypeInfo] = type_info

    def get(self, source_type: str) -> Any:
        """Return the adapter instance for the given source type.

        Args:
            source_type: The source-type string to look up.

        Returns:
            Any: The adapter instance (satisfies the ``SourceAdapter`` protocol).

        Raises:
            KeyError: If no adapter is registered for ``source_type``.
        """
        try:
            return self._type_map[source_type]
        except KeyError:
            raise KeyError(f"no adapter registered for source type: {source_type!r}") from None

    def all_handles(self) -> frozenset[str]:
        """Return all registered source-type strings.

        Returns:
            frozenset[str]: Every source type with an active adapter.
        """
        return frozenset(self._type_map.keys())

    def types_with_schema(self) -> list[AdapterTypeInfo]:
        """Return ordered AdapterTypeInfo for every registered type.

        Built-ins appear first (in their canonical order), then custom types
        sorted alphabetically.

        Returns:
            list[AdapterTypeInfo]: The ordered list.
        """
        return list(self._type_info)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Return the process-wide registry.

    Returns:
        AdapterRegistry: The initialised singleton.

    Raises:
        RuntimeError: If :func:`init_registry` has not been called yet.
    """
    if _registry is None:
        raise RuntimeError(
            "AdapterRegistry not initialized. Call init_registry() first."
        )
    return _registry


def init_registry(registry: AdapterRegistry) -> None:
    """Store the singleton registry.

    Args:
        registry: The fully-built registry returned by :func:`build_registry`.
    """
    global _registry
    _registry = registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_adapter(obj: Any) -> bool:
    """Return True if *obj* looks like a valid adapter class.

    Args:
        obj: The object to test.

    Returns:
        bool: True when obj has a non-empty ``handles`` sequence and a ``fetch``
        callable.
    """
    if not inspect.isclass(obj):
        return False
    handles = getattr(obj, "handles", None)
    if not handles or not isinstance(handles, (tuple, list)):
        return False
    if not all(isinstance(h, str) and h for h in handles):
        return False
    if not callable(getattr(obj, "fetch", None)):
        return False
    return True


def _adapter_meta(
    adapter_class: type[Any],
    *,
    fallback_display_name: str,
) -> tuple[tuple[str, ...], str, dict[str, Any], bool]:
    """Extract metadata from an adapter class with fallbacks.

    Args:
        adapter_class: The adapter class to inspect.
        fallback_display_name: Display name to use when the class has none.

    Returns:
        (handles, display_name, config_schema, multi_instance) tuple.
    """
    handles: tuple[str, ...] = tuple(adapter_class.handles)
    display_name: str = getattr(adapter_class, "display_name", fallback_display_name)
    config_schema: dict[str, Any] = getattr(adapter_class, "config_schema", {})
    multi_instance: bool = getattr(adapter_class, "multi_instance", True)
    return handles, display_name, config_schema, multi_instance


async def _upsert_adapter_plugin(
    sessionmaker: async_sessionmaker[Any],  # type: ignore[type-arg]
    *,
    slug: str,
    display_name: str,
    source: str,
    entry_point: str | None,
    filename: str | None,
    handles: list[str],
    config_schema: dict[str, Any],
    status: str,
    error: str | None,
) -> None:
    """Upsert a row in ``adapter_plugins`` using ON CONFLICT (slug) DO UPDATE.

    Args:
        sessionmaker: The async session factory.
        slug: Unique adapter slug.
        display_name: Human-readable name.
        source: Where the adapter came from — one of ``"builtin"``, ``"entrypoint"``, or ``"file"``.
        entry_point: Python entry-point string if loaded via entry-points.
        filename: Source filename if loaded via file-drop.
        handles: List of handled source-type strings.
        config_schema: JSON Schema dict.
        status: ``"loaded"`` or ``"error"``.
        error: Error message when status is ``"error"``.
    """
    row: dict[str, Any] = {
        "slug": slug,
        "display_name": display_name,
        "source": source,
        "entry_point": entry_point,
        "filename": filename,
        "handles": handles,
        "config_schema": config_schema,
        "status": status,
        "error": error,
    }
    stmt = pg_insert(AdapterPlugin).values(**row).on_conflict_do_update(
        index_elements=["slug"],
        set_=row,
    )
    async with sessionmaker() as session:
        await session.execute(stmt)
        await session.commit()


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


async def build_registry(
    sessionmaker: async_sessionmaker[Any],  # type: ignore[type-arg]
) -> AdapterRegistry:
    """Discover, load, and register all adapters; upsert DB rows.

    Loading order:
    1. Built-in adapters (GitHub, WPOrg, Webpage, REST Endpoint).
    2. Entry-point adapters (``wp_support_rag.adapters`` group).
    3. File-drop adapters from ``settings.custom_adapters_dir``.

    Args:
        sessionmaker: Async session factory used for DB upserts.

    Returns:
        AdapterRegistry: The fully-populated registry.
    """
    settings = get_settings()

    # Maps source_type -> adapter instance (active/winning adapter only)
    type_map: dict[str, Any] = {}

    # Maps source_type -> owning slug (to detect conflicts)
    type_owner: dict[str, str] = {}

    # Ordered list of AdapterTypeInfo for types_with_schema()
    builtin_infos: list[AdapterTypeInfo] = []
    custom_infos: list[AdapterTypeInfo] = []

    # Track which slugs are built-ins for conflict messaging
    builtin_slugs: set[str] = {slug for _, slug, _ in _BUILTINS}

    # -----------------------------------------------------------------------
    # 1. Built-in adapters
    # -----------------------------------------------------------------------
    for adapter_class, slug, forced_display_name in _BUILTINS:
        handles, display_name, config_schema, _ = _adapter_meta(
            adapter_class, fallback_display_name=forced_display_name
        )
        # Override display_name with the forced canonical value for built-ins
        display_name = forced_display_name

        instance = adapter_class()
        for source_type in handles:
            multi_instance = source_type not in _SINGLE_INSTANCE_TYPES
            type_map[source_type] = instance
            type_owner[source_type] = slug
            builtin_infos.append(
                AdapterTypeInfo(
                    source_type=source_type,
                    display_name=display_name,
                    adapter_slug=slug,
                    config_schema=config_schema,
                    is_builtin=True,
                    multi_instance=multi_instance,
                )
            )

        await _upsert_adapter_plugin(
            sessionmaker,
            slug=slug,
            display_name=display_name,
            source="builtin",
            entry_point=None,
            filename=None,
            handles=list(handles),
            config_schema=config_schema,
            status="loaded",
            error=None,
        )
        log.debug("Loaded built-in adapter %s handling %s", slug, handles)  # noqa: E501

    # -----------------------------------------------------------------------
    # 2. Entry-point adapters
    # -----------------------------------------------------------------------
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="wp_support_rag.adapters")
        for ep in eps:
            try:
                adapter_class = ep.load()
            except Exception as exc:
                log.warning("Failed to load entry-point adapter %r: %s", ep.name, exc)
                continue

            if not _is_valid_adapter(adapter_class):
                log.warning(
                    "Entry-point %r does not look like a valid adapter (missing handles/fetch)",
                    ep.name,
                )
                continue

            slug = f"ep.{ep.name}"
            handles, display_name, config_schema, multi_instance = _adapter_meta(
                adapter_class, fallback_display_name=adapter_class.__name__
            )

            conflict_errors: list[str] = []
            active_types: list[str] = []

            for source_type in handles:
                if source_type in type_owner:
                    owner_slug = type_owner[source_type]
                    msg = f"conflicts with built-in type: {source_type}" if owner_slug in builtin_slugs else f"conflicts with already-registered adapter: {owner_slug}"
                    conflict_errors.append(msg)
                else:
                    active_types.append(source_type)

            if conflict_errors:
                await _upsert_adapter_plugin(
                    sessionmaker,
                    slug=slug,
                    display_name=display_name,
                    source="entrypoint",
                    entry_point=ep.value,
                    filename=None,
                    handles=list(handles),
                    config_schema=config_schema,
                    status="error",
                    error="; ".join(conflict_errors),
                )
                log.warning(
                    "Entry-point adapter %r has conflicts: %s", slug, conflict_errors
                )
                # Even with conflicts, register non-conflicting types
                if active_types:
                    instance = adapter_class()
                    for source_type in active_types:
                        type_map[source_type] = instance
                        type_owner[source_type] = slug
                        custom_infos.append(
                            AdapterTypeInfo(
                                source_type=source_type,
                                display_name=display_name,
                                adapter_slug=slug,
                                config_schema=config_schema,
                                is_builtin=False,
                                multi_instance=True,
                            )
                        )
            else:
                instance = adapter_class()
                for source_type in handles:
                    type_map[source_type] = instance
                    type_owner[source_type] = slug
                    custom_infos.append(
                        AdapterTypeInfo(
                            source_type=source_type,
                            display_name=display_name,
                            adapter_slug=slug,
                            config_schema=config_schema,
                            is_builtin=False,
                            multi_instance=True,
                        )
                    )
                await _upsert_adapter_plugin(
                    sessionmaker,
                    slug=slug,
                    display_name=display_name,
                    source="entrypoint",
                    entry_point=ep.value,
                    filename=None,
                    handles=list(handles),
                    config_schema=config_schema,
                    status="loaded",
                    error=None,
                )
                log.debug("Loaded entry-point adapter %s handling %s", slug, handles)
    except Exception as exc:
        log.warning("Error scanning entry-point adapters: %s", exc)

    # -----------------------------------------------------------------------
    # 3. File-drop adapters
    # -----------------------------------------------------------------------
    custom_dir_str = settings.custom_adapters_dir
    if custom_dir_str:
        custom_dir = Path(custom_dir_str)
        if custom_dir.is_dir():
            for py_file in sorted(custom_dir.glob("*.py")):
                module_name = f"_custom_adapter_{py_file.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec is None or spec.loader is None:
                        log.warning("Could not load spec for %s", py_file)
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                except Exception as exc:
                    log.warning("Failed to load file adapter %s: %s", py_file, exc)
                    continue

                # Find all adapter classes in the module
                found_any = False
                for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ != module_name:
                        continue  # skip imported classes
                    if not _is_valid_adapter(obj):
                        continue

                    found_any = True
                    adapter_class = obj
                    slug = f"file.{py_file.stem}.{adapter_class.__name__}"
                    handles, display_name, config_schema, multi_instance = _adapter_meta(
                        adapter_class, fallback_display_name=adapter_class.__name__
                    )

                    conflict_errors_file: list[str] = []
                    active_types_file: list[str] = []

                    for source_type in handles:
                        if source_type in type_owner:
                            owner_slug = type_owner[source_type]
                            if owner_slug in builtin_slugs:
                                conflict_errors_file.append(
                                    f"conflicts with built-in type: {source_type}"
                                )
                            else:
                                conflict_errors_file.append(
                                    f"conflicts with already-registered adapter: {owner_slug}"
                                )
                        else:
                            active_types_file.append(source_type)

                    if conflict_errors_file:
                        await _upsert_adapter_plugin(
                            sessionmaker,
                            slug=slug,
                            display_name=display_name,
                            source="file",
                            entry_point=None,
                            filename=py_file.name,
                            handles=list(handles),
                            config_schema=config_schema,
                            status="error",
                            error="; ".join(conflict_errors_file),
                        )
                        log.warning(
                            "File adapter %r has conflicts: %s",
                            slug,
                            conflict_errors_file,
                        )
                        # Still register non-conflicting types
                        if active_types_file:
                            instance = adapter_class()
                            for source_type in active_types_file:
                                type_map[source_type] = instance
                                type_owner[source_type] = slug
                                custom_infos.append(
                                    AdapterTypeInfo(
                                        source_type=source_type,
                                        display_name=display_name,
                                        adapter_slug=slug,
                                        config_schema=config_schema,
                                        is_builtin=False,
                                        multi_instance=True,
                                    )
                                )
                    else:
                        instance = adapter_class()
                        for source_type in handles:
                            type_map[source_type] = instance
                            type_owner[source_type] = slug
                            custom_infos.append(
                                AdapterTypeInfo(
                                    source_type=source_type,
                                    display_name=display_name,
                                    adapter_slug=slug,
                                    config_schema=config_schema,
                                    is_builtin=False,
                                    multi_instance=True,
                                )
                            )
                        await _upsert_adapter_plugin(
                            sessionmaker,
                            slug=slug,
                            display_name=display_name,
                            source="file",
                            entry_point=None,
                            filename=py_file.name,
                            handles=list(handles),
                            config_schema=config_schema,
                            status="loaded",
                            error=None,
                        )
                        log.debug(
                            "Loaded file adapter %s handling %s", slug, handles
                        )

                if not found_any:
                    log.debug("No valid adapter class found in %s", py_file)
        else:
            log.debug(
                "custom_adapters_dir %r does not exist; skipping file-drop adapters",
                custom_dir_str,
            )

    # Sort custom infos alphabetically by source_type
    custom_infos.sort(key=lambda info: info.source_type)

    return AdapterRegistry(
        type_map=type_map,
        type_info=builtin_infos + custom_infos,
    )

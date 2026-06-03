"""Tests for AdapterRegistry: builtin loading, conflict detection, file-drop.

All tests that touch the database skip when no migrated PostgreSQL database is
reachable, following the same pattern used throughout this test suite.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.db.engine import get_sessionmaker
from app.ingestion.adapter_registry import (
    AdapterRegistry,
    AdapterTypeInfo,
    build_registry,
    get_registry,
    init_registry,
)
from sqlalchemy import select, text

from tests.conftest import database_available

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUILTIN_TYPES = frozenset(
    {
        "github_readme",
        "github_changelog",
        "github_docs",
        "github_issues",
        "wporg_faq",
        "wporg_changelog",
        "wporg_support",
        "webpage",
        "rest_endpoint",
    }
)

SINGLE_INSTANCE_TYPES = frozenset(
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

MULTI_INSTANCE_TYPES = frozenset({"webpage", "rest_endpoint"})

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_sessionmaker() -> Any:
    """Return a mock async_sessionmaker that records upsert calls.

    The session context manager commits silently; execute() is a no-op.
    """
    fake_session = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=False)
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()

    factory = MagicMock()
    factory.return_value = fake_session
    return factory


def _registry_without_db(custom_dir: str = "") -> AdapterRegistry:
    """Build a registry in isolation (no DB, no file-drop) for unit tests.

    Patches settings so custom_adapters_dir points at a nonexistent path, and
    replaces _upsert_adapter_plugin with a no-op so no DB is needed.
    """
    import asyncio

    from app.ingestion import adapter_registry as ar

    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = custom_dir
        mock_settings.return_value = cfg
        registry = asyncio.get_event_loop().run_until_complete(build_registry(fake_sm))
    return registry


# ---------------------------------------------------------------------------
# Unit tests (no DB required)
# ---------------------------------------------------------------------------


async def test_build_registry_builtins_no_db() -> None:
    """build_registry loads all 9 built-in source types without a live DB."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    assert BUILTIN_TYPES.issubset(registry.all_handles())


async def test_all_handles_contains_builtins_no_db() -> None:
    """all_handles() returns a frozenset covering every built-in type."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    handles = registry.all_handles()
    assert isinstance(handles, frozenset)
    for t in BUILTIN_TYPES:
        assert t in handles, f"expected {t!r} in all_handles()"


async def test_types_with_schema_ordering_no_db() -> None:
    """Builtin types appear before custom types in types_with_schema()."""
    fake_sm = _make_fake_sessionmaker()

    # Create a simple custom adapter module in tmp_path
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        adapter_code = textwrap.dedent(
            """\
            from collections.abc import AsyncIterator
            from typing import ClassVar

            class CustomAdapter:
                handles: ClassVar[tuple[str, ...]] = ("custom_zzz",)

                async def fetch(self, ctx):
                    return
                    yield  # make it an async generator
            """
        )
        adapter_file = Path(tmpdir) / "my_custom.py"
        adapter_file.write_text(adapter_code)

        with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
             patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
            cfg = MagicMock()
            cfg.custom_adapters_dir = tmpdir
            mock_settings.return_value = cfg
            registry = await build_registry(fake_sm)

    infos = registry.types_with_schema()
    source_types = [i.source_type for i in infos]

    # All builtin types must appear before custom_zzz
    if "custom_zzz" in source_types:
        custom_idx = source_types.index("custom_zzz")
        for btype in BUILTIN_TYPES:
            builtin_idx = source_types.index(btype)
            assert builtin_idx < custom_idx, (
                f"builtin {btype!r} should appear before custom_zzz"
            )


async def test_get_raises_key_error_for_unknown_type_no_db() -> None:
    """get() raises KeyError for an unregistered source type."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    with pytest.raises(KeyError, match="no adapter registered"):
        registry.get("nonexistent_type_xyz")


async def test_file_adapter_loaded_no_db(tmp_path: Path) -> None:
    """A valid .py file-drop adapter is loaded and its type becomes available."""
    adapter_code = textwrap.dedent(
        """\
        from collections.abc import AsyncIterator
        from typing import ClassVar

        class MyFileAdapter:
            handles: ClassVar[tuple[str, ...]] = ("custom_filedrop",)
            display_name: ClassVar[str] = "My File Adapter"
            config_schema: ClassVar[dict] = {"type": "object"}

            async def fetch(self, ctx):
                return
                yield
        """
    )
    (tmp_path / "myadapter.py").write_text(adapter_code)

    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = str(tmp_path)
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    assert "custom_filedrop" in registry.all_handles()
    assert registry.get("custom_filedrop") is not None

    infos = registry.types_with_schema()
    custom_info = next((i for i in infos if i.source_type == "custom_filedrop"), None)
    assert custom_info is not None
    assert custom_info.is_builtin is False
    assert custom_info.multi_instance is True
    assert custom_info.adapter_slug.startswith("file.")


async def test_builtin_conflict_gets_error_status_no_db(tmp_path: Path) -> None:
    """A file adapter claiming a builtin type is upserted with status='error'."""
    adapter_code = textwrap.dedent(
        """\
        from collections.abc import AsyncIterator
        from typing import ClassVar

        class ConflictAdapter:
            handles: ClassVar[tuple[str, ...]] = ("github_readme",)

            async def fetch(self, ctx):
                return
                yield
        """
    )
    (tmp_path / "conflict.py").write_text(adapter_code)

    fake_sm = _make_fake_sessionmaker()
    upsert_calls: list[dict] = []

    async def capture_upsert(_sm: Any, **kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch(
             "app.ingestion.adapter_registry._upsert_adapter_plugin",
             side_effect=capture_upsert,
         ):
        cfg = MagicMock()
        cfg.custom_adapters_dir = str(tmp_path)
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    # The conflicting adapter's upsert call should have status='error'
    conflict_calls = [c for c in upsert_calls if c.get("slug", "").startswith("file.")]
    assert conflict_calls, "expected at least one file adapter upsert call"
    conflict_call = conflict_calls[0]
    assert conflict_call["status"] == "error"
    assert "conflicts with built-in type" in conflict_call["error"]

    # The builtin type must still be registered correctly
    assert "github_readme" in registry.all_handles()


async def test_custom_to_custom_conflict_no_db(tmp_path: Path) -> None:
    """When two file adapters claim the same type, first wins and second errors."""
    first_code = textwrap.dedent(
        """\
        from typing import ClassVar

        class FirstAdapter:
            handles: ClassVar[tuple[str, ...]] = ("custom_shared",)

            async def fetch(self, ctx):
                return
                yield
        """
    )
    second_code = textwrap.dedent(
        """\
        from typing import ClassVar

        class SecondAdapter:
            handles: ClassVar[tuple[str, ...]] = ("custom_shared",)

            async def fetch(self, ctx):
                return
                yield
        """
    )
    # Name files so 'aaa_first' sorts before 'zzz_second'
    (tmp_path / "aaa_first.py").write_text(first_code)
    (tmp_path / "zzz_second.py").write_text(second_code)

    fake_sm = _make_fake_sessionmaker()
    upsert_calls: list[dict] = []

    async def capture_upsert(_sm: Any, **kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch(
             "app.ingestion.adapter_registry._upsert_adapter_plugin",
             side_effect=capture_upsert,
         ):
        cfg = MagicMock()
        cfg.custom_adapters_dir = str(tmp_path)
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    # custom_shared should be registered (from first adapter)
    assert "custom_shared" in registry.all_handles()

    # Find file adapter upsert calls
    file_calls = [c for c in upsert_calls if c.get("slug", "").startswith("file.")]
    assert len(file_calls) >= 2

    # The second adapter (zzz_second) should have status='error'
    second_calls = [c for c in file_calls if "zzz_second" in c.get("slug", "")]
    assert second_calls, "expected upsert call for zzz_second"
    assert second_calls[0]["status"] == "error"


async def test_multi_instance_rules_no_db() -> None:
    """Built-in github/wporg types have multi_instance=False; webpage/rest=True."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    infos_by_type = {i.source_type: i for i in registry.types_with_schema()}

    for source_type in SINGLE_INSTANCE_TYPES:
        assert infos_by_type[source_type].multi_instance is False, (
            f"{source_type} should have multi_instance=False"
        )

    for source_type in MULTI_INSTANCE_TYPES:
        assert infos_by_type[source_type].multi_instance is True, (
            f"{source_type} should have multi_instance=True"
        )


async def test_builtin_adapters_are_flagged_as_builtin_no_db() -> None:
    """AdapterTypeInfo.is_builtin is True for all built-in source types."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    infos_by_type = {i.source_type: i for i in registry.types_with_schema()}
    for source_type in BUILTIN_TYPES:
        assert infos_by_type[source_type].is_builtin is True, (
            f"{source_type} should be marked is_builtin=True"
        )


# ---------------------------------------------------------------------------
# Singleton helpers (unit, no DB)
# ---------------------------------------------------------------------------


async def test_get_registry_raises_before_init() -> None:
    """get_registry() raises RuntimeError when not yet initialised."""
    import app.ingestion.adapter_registry as ar

    original = ar._registry
    try:
        ar._registry = None
        with pytest.raises(RuntimeError, match="not initialized"):
            get_registry()
    finally:
        ar._registry = original


async def test_init_registry_sets_singleton() -> None:
    """init_registry() stores the registry and get_registry() returns it."""
    import app.ingestion.adapter_registry as ar

    original = ar._registry
    try:
        fake_registry = AdapterRegistry(type_map={}, type_info=[])
        init_registry(fake_registry)
        assert get_registry() is fake_registry
    finally:
        ar._registry = original


async def test_adapter_type_info_fields_no_db() -> None:
    """AdapterTypeInfo carries expected field names and types."""
    fake_sm = _make_fake_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_settings, \
         patch("app.ingestion.adapter_registry._upsert_adapter_plugin", new_callable=AsyncMock):
        cfg = MagicMock()
        cfg.custom_adapters_dir = ""
        mock_settings.return_value = cfg
        registry = await build_registry(fake_sm)

    infos = registry.types_with_schema()
    assert len(infos) >= 9
    for info in infos:
        assert isinstance(info, AdapterTypeInfo)
        assert isinstance(info.source_type, str) and info.source_type
        assert isinstance(info.display_name, str) and info.display_name
        assert isinstance(info.adapter_slug, str) and info.adapter_slug
        assert isinstance(info.config_schema, dict)
        assert isinstance(info.is_builtin, bool)
        assert isinstance(info.multi_instance, bool)


# ---------------------------------------------------------------------------
# DB integration tests (skip when DB unreachable)
# ---------------------------------------------------------------------------


async def test_build_registry_upserts_builtins_to_db() -> None:
    """build_registry upserts all four built-in adapter rows into adapter_plugins."""
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")

    from app.db.models import AdapterPlugin

    sm = get_sessionmaker()
    registry = await build_registry(sm)

    async with sm() as session:
        result = await session.execute(
            select(AdapterPlugin).where(AdapterPlugin.source.in_(["builtin"]))
        )
        rows = result.scalars().all()

    builtin_slugs = {r.slug for r in rows}
    assert "builtin.github" in builtin_slugs
    assert "builtin.wporg" in builtin_slugs
    assert "builtin.webpage" in builtin_slugs
    assert "builtin.rest_endpoint" in builtin_slugs

    # All built-ins should be status='loaded'
    for row in rows:
        assert row.status == "loaded", f"{row.slug} should be status=loaded"


async def test_build_registry_db_handles_all_builtins() -> None:
    """After build_registry, all 9 builtin source types are reachable via get()."""
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")

    sm = get_sessionmaker()
    registry = await build_registry(sm)

    for source_type in BUILTIN_TYPES:
        adapter = registry.get(source_type)
        assert adapter is not None, f"get({source_type!r}) returned None"


async def test_file_adapter_conflict_status_in_db(tmp_path: Path) -> None:
    """A conflicting file adapter gets status='error' in the DB."""
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")

    from app.db.models import AdapterPlugin

    adapter_code = textwrap.dedent(
        """\
        from typing import ClassVar

        class DBConflictAdapter:
            handles: ClassVar[tuple[str, ...]] = ("github_readme",)

            async def fetch(self, ctx):
                return
                yield
        """
    )
    (tmp_path / "dbconflict.py").write_text(adapter_code)

    sm = get_sessionmaker()

    with patch("app.ingestion.adapter_registry.get_settings") as mock_ar_gs:
        cfg = MagicMock()
        cfg.custom_adapters_dir = str(tmp_path)
        mock_ar_gs.return_value = cfg

        registry = await build_registry(sm)

    # Find the conflict row in the DB
    conflict_slug = "file.dbconflict.DBConflictAdapter"
    async with sm() as session:
        result = await session.execute(
            select(AdapterPlugin).where(AdapterPlugin.slug == conflict_slug)
        )
        row = result.scalar_one_or_none()

    if row is not None:
        assert row.status == "error"
        assert "conflicts with built-in type" in (row.error or "")

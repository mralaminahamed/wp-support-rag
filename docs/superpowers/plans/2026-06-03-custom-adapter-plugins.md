# Custom Adapter Plugin System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow internal developers and third-party companies to package custom ingestion adapters and install them into wp-support-rag without modifying core code.

**Architecture:** A startup-time `AdapterRegistry` singleton (in `app/ingestion/adapter_registry.py`) discovers built-in, pip entry-point, and file-drop adapters; upserts `adapter_plugins` DB rows; and replaces the static `_ADAPTERS` dict in `tasks.py`. Source type validation moves from a DB CHECK constraint to app-layer registry lookup. Frontend `AddSourceModal` fetches available types from API instead of using a hardcoded list.

**Tech Stack:** Python `importlib.metadata`, FastAPI lifespan, `celery.signals.worker_init`, SQLAlchemy 2.0 async, Alembic migration, `python-multipart` (file upload), React + TanStack Query, dynamic JSON Schema form renderer.

---

## File Map

**New backend files:**
- `packages/wp_support_rag_sdk/wp_support_rag_sdk/adapter.py` — canonical SourceAdapter, SourceContext, RawDocument, SourceFetchError, ContentType definitions
- `packages/wp_support_rag_sdk/wp_support_rag_sdk/__init__.py` — re-exports
- `packages/wp_support_rag_sdk/pyproject.toml` — standalone package metadata
- `apps/api/app/ingestion/adapter_registry.py` — AdapterRegistry, AdapterTypeInfo, init_registry(), get_registry()
- `apps/api/app/api/routes_adapters.py` — GET/POST/DELETE /adapter-plugins routes
- `apps/api/app/db/migrations/versions/20260603_0011_custom_adapter_plugins.py` — drop check constraint, create adapter_plugins table
- `apps/api/tests/test_adapter_registry.py`
- `apps/api/tests/test_routes_adapters.py`

**New frontend files:**
- `apps/admin/src/components/JsonSchemaForm.tsx` — dynamic form from JSON Schema
- `apps/admin/src/pages/AdaptersPage.tsx` — adapter management page

**Modified backend files:**
- `apps/api/app/ingestion/adapters/base.py` — import types from wp_support_rag_sdk
- `apps/api/app/db/models.py` — add AdapterPlugin ORM model
- `apps/api/app/config.py` — add custom_adapters_dir setting
- `apps/api/app/main.py` — call init_registry() in lifespan, include adapters router
- `apps/api/app/ingestion/tasks.py` — replace _ADAPTERS with get_registry(), add worker_init signal
- `apps/api/app/ingestion/registry.py` — remove SOURCE_TYPES check in add_source()
- `apps/api/app/api/schemas.py` — add AdapterPluginSummary, AdapterTypeInfo schemas
- `apps/api/pyproject.toml` — add python-multipart dep, add wp_support_rag_sdk path dep

**Modified frontend files:**
- `apps/admin/src/types/api.ts` — add AdapterTypeInfo, AdapterPluginSummary interfaces
- `apps/admin/src/api/admin.ts` — add getAdapterTypes, listAdapterPlugins, uploadAdapterPlugin, deleteAdapterPlugin
- `apps/admin/src/features/AddSourceModal.tsx` — replace hardcoded SOURCE_TYPES with API query, add JsonSchemaForm for custom types
- `apps/admin/src/app/routes.tsx` — add /adapters route
- `apps/admin/src/components/layout/AppShell.tsx` — add Adapters nav entry

**Modified infra files:**
- `docker-compose.yml` — add custom_adapters volume to app and worker services

---

## Task 1: SDK Package — Canonical Adapter Types

**Files:**
- Create: `packages/wp_support_rag_sdk/wp_support_rag_sdk/adapter.py`
- Create: `packages/wp_support_rag_sdk/wp_support_rag_sdk/__init__.py`
- Create: `packages/wp_support_rag_sdk/pyproject.toml`
- Modify: `apps/api/app/ingestion/adapters/base.py`
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1: Create the SDK package directory structure**

```bash
mkdir -p packages/wp_support_rag_sdk/wp_support_rag_sdk
```

- [ ] **Step 2: Create `packages/wp_support_rag_sdk/wp_support_rag_sdk/adapter.py`**

This file contains the canonical definitions — copy the type definitions from `app/ingestion/adapters/base.py`:

```python
"""Canonical adapter interface types for wp-support-rag.

External adapter developers import from this package:
    from wp_support_rag_sdk import SourceAdapter, SourceContext, RawDocument
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

ContentType = Literal["markdown", "html", "text"]


class SourceFetchError(Exception):
    """Raised on an unrecoverable upstream failure after retries."""


class RawDocument(BaseModel):
    external_id: str
    title: str | None = None
    doc_type: str
    content: str
    content_type: ContentType
    source_url: str
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceContext(BaseModel):
    plugin_slug: str
    source_type: str
    github_repo: str | None = None
    wporg_slug: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    etags: dict[str, str] = Field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    handles: ClassVar[tuple[str, ...]]

    def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]: ...
```

- [ ] **Step 3: Create `packages/wp_support_rag_sdk/wp_support_rag_sdk/__init__.py`**

```python
from wp_support_rag_sdk.adapter import (
    ContentType,
    RawDocument,
    SourceAdapter,
    SourceContext,
    SourceFetchError,
)

__all__ = [
    "ContentType",
    "RawDocument",
    "SourceAdapter",
    "SourceContext",
    "SourceFetchError",
]
```

- [ ] **Step 4: Create `packages/wp_support_rag_sdk/pyproject.toml`**

```toml
[project]
name = "wp-support-rag-sdk"
version = "0.1.0"
description = "Adapter interface types for wp-support-rag custom adapters."
requires-python = ">=3.12"
dependencies = ["pydantic>=2.9"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 5: Update `apps/api/app/ingestion/adapters/base.py` to import from SDK**

Replace the entire file content:

```python
"""Source adapter contract — re-exported from wp_support_rag_sdk.

All adapter implementations and the ingestion pipeline import from here.
External adapter developers import from wp_support_rag_sdk directly.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from wp_support_rag_sdk.adapter import (
    ContentType,
    RawDocument,
    SourceAdapter,
    SourceContext,
    SourceFetchError,
)

__all__ = [
    "ContentType",
    "RawDocument",
    "SourceAdapter",
    "SourceContext",
    "SourceFetchError",
]
```

- [ ] **Step 6: Add SDK path dependency and python-multipart to `apps/api/pyproject.toml`**

In the `dependencies` list, add:
```toml
"python-multipart>=0.0.12",
"wp-support-rag-sdk",
```

Add a `[tool.uv.sources]` section (or extend existing):
```toml
[tool.uv.sources]
wp-support-rag-sdk = { path = "../../packages/wp_support_rag_sdk", editable = true }
```

- [ ] **Step 7: Install and verify imports work**

```bash
cd apps/api
uv sync
python -c "from app.ingestion.adapters.base import SourceAdapter, RawDocument, SourceContext; print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Run existing adapter tests to confirm nothing broke**

```bash
cd apps/api
uv run pytest tests/test_webpage_adapter.py tests/test_rest_endpoint_adapter.py -v
```

Expected: 10 passed.

- [ ] **Step 9: Commit**

```bash
git add packages/wp_support_rag_sdk/ apps/api/app/ingestion/adapters/base.py apps/api/pyproject.toml
git commit -m "feat(sdk): extract adapter interface types into wp_support_rag_sdk package"
```

---

## Task 2: DB Migration 0011 — Drop Check Constraint, Create adapter_plugins

**Files:**
- Create: `apps/api/app/db/migrations/versions/20260603_0011_custom_adapter_plugins.py`

- [ ] **Step 1: Create the migration file**

```python
"""Drop sources_source_type_check; create adapter_plugins table.

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-03

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the hardcoded source_type CHECK — validation moves to app layer.
    op.drop_constraint("sources_source_type_check", "sources", type_="check")

    # Create the adapter_plugins metadata table.
    op.create_table(
        "adapter_plugins",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("entry_point", sa.Text(), nullable=True),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("handles", ARRAY(sa.Text()), nullable=False),
        sa.Column("config_schema", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'loaded'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("slug", name="adapter_plugins_slug_key"),
        sa.CheckConstraint(
            "source IN ('builtin','entrypoint','file')",
            name="adapter_plugins_source_check",
        ),
        sa.CheckConstraint(
            "status IN ('loaded','error','disabled')",
            name="adapter_plugins_status_check",
        ),
    )


def downgrade() -> None:
    op.drop_table("adapter_plugins")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support',"
        "'webpage','rest_endpoint')",
    )
```

- [ ] **Step 2: Apply migration**

```bash
cd apps/api
uv run alembic upgrade head
```

Expected output ends with: `Running upgrade 0010 -> 0011, Drop sources_source_type_check; create adapter_plugins table.`

- [ ] **Step 3: Verify in DB**

```bash
docker compose exec postgres psql -U wprag -d wprag -c "\d adapter_plugins"
```

Expected: table with columns id, slug, display_name, version, source, entry_point, filename, handles, config_schema, status, error, installed_at.

```bash
docker compose exec postgres psql -U wprag -d wprag -c "\d sources" | grep "sources_source_type"
```

Expected: no output (constraint dropped).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/db/migrations/versions/20260603_0011_custom_adapter_plugins.py
git commit -m "feat(db): drop source_type check constraint, create adapter_plugins table"
```

---

## Task 3: AdapterPlugin ORM Model

**Files:**
- Modify: `apps/api/app/db/models.py`

- [ ] **Step 1: Add `AdapterPlugin` class to the end of `apps/api/app/db/models.py`**

Add after the last model class (before any trailing code):

```python
class AdapterPlugin(Base):
    """Metadata row for a discovered adapter (builtin, entrypoint, or file).

    Attributes:
        id: Surrogate primary key.
        slug: Unique machine identifier, e.g. ``builtin.github`` or ``acme.salesforce``.
        display_name: Human-readable name shown in the admin UI.
        version: Package version string (entrypoint adapters only).
        source: How this adapter was discovered: ``builtin``, ``entrypoint``, or ``file``.
        entry_point: Entry point string (entrypoint adapters only).
        filename: Source filename (file adapters only).
        handles: Source type strings this adapter owns.
        config_schema: JSON Schema for the adapter's config fields.
        status: ``loaded``, ``error``, or ``disabled``.
        error: Error message when ``status='error'``.
        installed_at: When the row was first created.
    """

    __tablename__ = "adapter_plugins"
    __table_args__ = (
        CheckConstraint(
            "source IN ('builtin','entrypoint','file')",
            name="adapter_plugins_source_check",
        ),
        CheckConstraint(
            "status IN ('loaded','error','disabled')",
            name="adapter_plugins_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    entry_point: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    handles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    config_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'loaded'"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
```

The `datetime` import is already present (check existing models use it). `ARRAY`, `JSONB`, `Text`, `CheckConstraint`, `_uuid_pk`, `mapped_column`, `Mapped` are all already imported.

- [ ] **Step 2: Verify import works**

```bash
cd apps/api
python -c "from app.db.models import AdapterPlugin; print(AdapterPlugin.__tablename__)"
```

Expected: `adapter_plugins`

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/db/models.py
git commit -m "feat(models): add AdapterPlugin ORM model"
```

---

## Task 4: Config — custom_adapters_dir Setting

**Files:**
- Modify: `apps/api/app/config.py`

- [ ] **Step 1: Add field to `Settings` class in `apps/api/app/config.py`**

Find the section with other path/directory settings (near `admin_url`) and add:

```python
custom_adapters_dir: str = Field(
    default="/app/custom_adapters",
    description="Directory scanned for file-drop adapter .py files. Empty string disables.",
)
```

- [ ] **Step 2: Verify**

```bash
cd apps/api
python -c "from app.config import get_settings; s = get_settings(); print(s.custom_adapters_dir)"
```

Expected: `/app/custom_adapters`

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/config.py
git commit -m "feat(config): add custom_adapters_dir setting"
```

---

## Task 5: AdapterRegistry — Core Implementation

**Files:**
- Create: `apps/api/app/ingestion/adapter_registry.py`
- Create: `apps/api/tests/test_adapter_registry.py`

- [ ] **Step 1: Write failing tests first**

Create `apps/api/tests/test_adapter_registry.py`:

```python
"""Unit tests for AdapterRegistry."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ingestion.adapter_registry import (
    AdapterRegistry,
    AdapterTypeInfo,
    _validate_adapter_class,
    _load_adapter_classes_from_file,
)
from wp_support_rag_sdk import RawDocument, SourceContext


# ── helpers ──────────────────────────────────────────────────────────────────

class GoodAdapter:
    handles: ClassVar[tuple[str, ...]] = ("test_type",)
    display_name: ClassVar[str] = "Test Adapter"
    config_schema: ClassVar[dict] = {}
    multi_instance: ClassVar[bool] = True

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        yield RawDocument(
            external_id="x", doc_type="test_type",
            content="c", content_type="text", source_url="http://x.com",
        )


class NoHandles:
    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        yield  # type: ignore


class EmptyHandles:
    handles: ClassVar[tuple[str, ...]] = ()
    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        yield  # type: ignore


class NoFetch:
    handles: ClassVar[tuple[str, ...]] = ("bad_type",)


# ── _validate_adapter_class ───────────────────────────────────────────────────

def test_validate_good_adapter_returns_none():
    assert _validate_adapter_class(GoodAdapter) is None


def test_validate_no_handles_returns_error():
    err = _validate_adapter_class(NoHandles)
    assert err is not None
    assert "handles" in err


def test_validate_empty_handles_returns_error():
    err = _validate_adapter_class(EmptyHandles)
    assert err is not None
    assert "empty" in err


def test_validate_no_fetch_returns_error():
    err = _validate_adapter_class(NoFetch)
    assert err is not None
    assert "fetch" in err


# ── _load_adapter_classes_from_file ──────────────────────────────────────────

def test_load_valid_file(tmp_path: Path):
    adapter_file = tmp_path / "my_adapter.py"
    adapter_file.write_text(
        "from typing import ClassVar, AsyncIterator\n"
        "from wp_support_rag_sdk import SourceContext, RawDocument\n\n"
        "class MyAdapter:\n"
        "    handles: ClassVar[tuple[str, ...]] = ('my_custom_type',)\n"
        "    display_name: ClassVar[str] = 'My Adapter'\n"
        "    config_schema: ClassVar[dict] = {}\n"
        "    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:\n"
        "        yield RawDocument(external_id='x', doc_type='my_custom_type',\n"
        "                          content='c', content_type='text', source_url='http://x.com')\n"
    )
    classes, err = _load_adapter_classes_from_file(adapter_file)
    assert err is None
    assert len(classes) == 1
    assert classes[0].handles == ("my_custom_type",)


def test_load_invalid_file_syntax(tmp_path: Path):
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def this is not valid python!!!")
    classes, err = _load_adapter_classes_from_file(bad_file)
    assert classes == []
    assert err is not None
    assert "import error" in err.lower() or "syntax" in err.lower()


def test_load_file_no_adapter_classes(tmp_path: Path):
    plain_file = tmp_path / "plain.py"
    plain_file.write_text("x = 1\n")
    classes, err = _load_adapter_classes_from_file(plain_file)
    assert classes == []
    assert err is not None
    assert "no adapter" in err.lower()


# ── AdapterRegistry ───────────────────────────────────────────────────────────

def test_registry_get_known_type():
    registry = AdapterRegistry()
    registry._register_builtin(GoodAdapter, slug="builtin.test")
    adapter = registry.get("test_type")
    assert adapter is not None


def test_registry_get_unknown_type_raises():
    registry = AdapterRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent_type")


def test_registry_all_handles_includes_registered():
    registry = AdapterRegistry()
    registry._register_builtin(GoodAdapter, slug="builtin.test")
    assert "test_type" in registry.all_handles()


def test_registry_conflict_with_builtin_returns_error():
    registry = AdapterRegistry()
    registry._register_builtin(GoodAdapter, slug="builtin.test")

    class Conflicting:
        handles: ClassVar[tuple[str, ...]] = ("test_type",)
        display_name: ClassVar[str] = "Conflicting"
        config_schema: ClassVar[dict] = {}
        async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
            yield  # type: ignore

    err = registry._register_custom(Conflicting, slug="custom.conflicting", source="file")
    assert err is not None
    assert "conflict" in err.lower()


def test_registry_types_with_schema_returns_all():
    registry = AdapterRegistry()
    registry._register_builtin(GoodAdapter, slug="builtin.test")
    types = registry.types_with_schema()
    assert any(t.source_type == "test_type" for t in types)
```

- [ ] **Step 2: Run tests to verify they all fail (module missing)**

```bash
cd apps/api
uv run pytest tests/test_adapter_registry.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.ingestion.adapter_registry'`

- [ ] **Step 3: Create `apps/api/app/ingestion/adapter_registry.py`**

```python
"""Adapter discovery and registry.

Discovers built-in, pip entry-point, and file-drop adapters at startup.
Upserts adapter_plugins DB rows. Provides get(source_type) and all_handles()
to replace the static _ADAPTERS dict in tasks.py.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AdapterPlugin
from app.ingestion.adapters.base import SourceAdapter, SourceContext
from wp_support_rag_sdk import RawDocument

logger = logging.getLogger(__name__)

# Built-in type strings that are single-instance (one per plugin).
_SINGLE_INSTANCE_BUILTINS = frozenset({
    "github_readme", "github_changelog", "github_docs", "github_issues",
    "wporg_faq", "wporg_changelog", "wporg_support",
})

# Module-level singleton set by init_registry().
_registry: "AdapterRegistry | None" = None


def get_registry() -> "AdapterRegistry":
    """Return the initialized registry. Raises RuntimeError if not initialized."""
    if _registry is None:
        raise RuntimeError("AdapterRegistry not initialized — call init_registry() first")
    return _registry


class AdapterTypeInfo(BaseModel):
    """Describes one source type available in the registry."""

    source_type: str
    display_name: str
    adapter_slug: str
    config_schema: dict[str, Any]
    is_builtin: bool
    multi_instance: bool


class AdapterRegistry:
    """In-memory registry of all loaded adapters, keyed by source type."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}
        self._type_info: dict[str, AdapterTypeInfo] = {}

    # ── public interface ──────────────────────────────────────────────────────

    def get(self, source_type: str) -> SourceAdapter:
        """Return adapter for source_type. Raises KeyError if unknown."""
        return self._adapters[source_type]

    def all_handles(self) -> frozenset[str]:
        """All registered source type strings."""
        return frozenset(self._adapters)

    def types_with_schema(self) -> list[AdapterTypeInfo]:
        """Ordered list: built-ins first, then custom alphabetically."""
        builtins = [i for i in self._type_info.values() if i.is_builtin]
        customs = sorted(
            [i for i in self._type_info.values() if not i.is_builtin],
            key=lambda i: i.source_type,
        )
        return builtins + customs

    # ── internal registration ─────────────────────────────────────────────────

    def _register_builtin(self, cls: type, *, slug: str) -> None:
        """Register a built-in adapter. Never fails."""
        instance = cls()
        multi = getattr(cls, "multi_instance", False)
        display = getattr(cls, "display_name", slug)
        schema = getattr(cls, "config_schema", {})
        for handle in cls.handles:
            self._adapters[handle] = instance
            self._type_info[handle] = AdapterTypeInfo(
                source_type=handle,
                display_name=display if len(cls.handles) == 1 else f"{display} ({handle})",
                adapter_slug=slug,
                config_schema=schema,
                is_builtin=True,
                multi_instance=handle not in _SINGLE_INSTANCE_BUILTINS,
            )

    def _register_custom(
        self, cls: type, *, slug: str, source: str,
    ) -> str | None:
        """Register a custom adapter. Returns error string on conflict, None on success."""
        instance = cls()
        multi = getattr(cls, "multi_instance", True)
        display = getattr(cls, "display_name", slug)
        schema = getattr(cls, "config_schema", {})
        conflicts = [h for h in cls.handles if h in self._adapters]
        if conflicts:
            existing_slugs = {self._type_info[h].adapter_slug for h in conflicts}
            is_builtin_conflict = any(self._type_info[h].is_builtin for h in conflicts)
            kind = "built-in" if is_builtin_conflict else "another adapter"
            return f"conflicts with {kind} type(s): {', '.join(conflicts)}"
        for handle in cls.handles:
            self._adapters[handle] = instance
            self._type_info[handle] = AdapterTypeInfo(
                source_type=handle,
                display_name=display if len(cls.handles) == 1 else f"{display} ({handle})",
                adapter_slug=slug,
                config_schema=schema,
                is_builtin=False,
                multi_instance=multi,
            )
        return None


# ── file loading helpers ──────────────────────────────────────────────────────

def _validate_adapter_class(cls: type) -> str | None:
    """Return error message if cls is not a valid adapter, None if valid."""
    handles = getattr(cls, "handles", None)
    if handles is None:
        return "missing 'handles' class attribute"
    if not isinstance(handles, tuple) or len(handles) == 0:
        return "'handles' must be a non-empty tuple"
    for h in handles:
        if not isinstance(h, str) or not h or " " in h:
            return f"invalid handle value: {h!r}"
    fetch = getattr(cls, "fetch", None)
    if fetch is None or not callable(fetch):
        return "missing 'fetch' method"
    if not inspect.isasyncgenfunction(fetch):
        return "'fetch' must be an async generator function"
    return None


def _load_adapter_classes_from_file(
    path: Path,
) -> tuple[list[type], str | None]:
    """Import a .py file and return (adapter_classes, error).

    Returns ([], error_message) on any failure.
    Returns (classes, None) on success; classes may be empty if no adapters found.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return [], "could not create module spec"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        return [], f"import error: {exc}"

    classes = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module.__name__
        and hasattr(obj, "handles")
        and hasattr(obj, "fetch")
    ]
    if not classes:
        return [], "no adapter classes found (need 'handles' + 'fetch')"
    return classes, None


# ── DB upsert ─────────────────────────────────────────────────────────────────

async def _upsert_adapter_row(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
    version: str | None,
    source: str,
    entry_point: str | None,
    filename: str | None,
    handles: list[str],
    config_schema: dict[str, Any],
    status: str,
    error: str | None,
) -> None:
    existing = (
        await session.execute(
            select(AdapterPlugin).where(AdapterPlugin.slug == slug)
        )
    ).scalar_one_or_none()
    if existing is None:
        row = AdapterPlugin(
            slug=slug,
            display_name=display_name,
            version=version,
            source=source,
            entry_point=entry_point,
            filename=filename,
            handles=handles,
            config_schema=config_schema,
            status=status,
            error=error,
        )
        session.add(row)
    else:
        existing.display_name = display_name
        existing.version = version
        existing.handles = handles
        existing.config_schema = config_schema
        existing.status = status
        existing.error = error
    await session.flush()


# ── startup entry point ───────────────────────────────────────────────────────

async def init_registry(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> "AdapterRegistry":
    """Build registry, upsert DB rows, set module-level singleton."""
    global _registry
    _registry = await _build_registry(sessionmaker)
    return _registry


async def _build_registry(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AdapterRegistry:
    """Discover all adapters and upsert adapter_plugins rows."""
    from app.config import get_settings
    from app.ingestion.adapters.github import GitHubAdapter
    from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter
    from app.ingestion.adapters.webpage import WebpageAdapter
    from app.ingestion.adapters.wporg import WporgAdapter

    settings = get_settings()
    registry = AdapterRegistry()

    # 1. Built-ins
    builtins = [
        (GitHubAdapter,       "builtin.github"),
        (WporgAdapter,        "builtin.wporg"),
        (WebpageAdapter,      "builtin.webpage"),
        (RestEndpointAdapter, "builtin.rest_endpoint"),
    ]
    for cls, slug in builtins:
        registry._register_builtin(cls, slug=slug)
        display = getattr(cls, "display_name", slug)
        schema = getattr(cls, "config_schema", {})
        async with sessionmaker() as session:
            await _upsert_adapter_row(
                session,
                slug=slug,
                display_name=display,
                version=None,
                source="builtin",
                entry_point=None,
                filename=None,
                handles=list(cls.handles),
                config_schema=schema,
                status="loaded",
                error=None,
            )
            await session.commit()

    # 2. Entry points
    try:
        eps = importlib.metadata.entry_points(group="wp_support_rag.adapters")
    except Exception:
        eps = []
    for ep in eps:
        slug = f"entrypoint.{ep.name}"
        try:
            cls = ep.load()
            validation_err = _validate_adapter_class(cls)
        except Exception as exc:
            validation_err = str(exc)
            cls = None

        if validation_err or cls is None:
            status, error = "error", validation_err or "failed to load"
            handles: list[str] = []
            display = ep.name
            schema: dict[str, Any] = {}
        else:
            conflict_err = registry._register_custom(cls, slug=slug, source="entrypoint")
            if conflict_err:
                status, error = "error", conflict_err
                handles = list(cls.handles)
            else:
                status, error = "loaded", None
                handles = list(cls.handles)
            display = getattr(cls, "display_name", ep.name)
            schema = getattr(cls, "config_schema", {})

        try:
            dist = importlib.metadata.packages_distributions()
            version = None  # simplified — full version lookup not critical
        except Exception:
            version = None

        async with sessionmaker() as session:
            await _upsert_adapter_row(
                session,
                slug=slug,
                display_name=display,
                version=version,
                source="entrypoint",
                entry_point=str(ep),
                filename=None,
                handles=handles,
                config_schema=schema,
                status=status,
                error=error,
            )
            await session.commit()

    # 3. File-drop
    adapters_dir = settings.custom_adapters_dir
    if adapters_dir:
        dir_path = Path(adapters_dir)
        if dir_path.is_dir():
            for py_file in sorted(dir_path.glob("*.py")):
                slug = f"file.{py_file.stem}"
                classes, load_err = _load_adapter_classes_from_file(py_file)
                if load_err:
                    async with sessionmaker() as session:
                        await _upsert_adapter_row(
                            session,
                            slug=slug,
                            display_name=py_file.stem,
                            version=None,
                            source="file",
                            entry_point=None,
                            filename=py_file.name,
                            handles=[],
                            config_schema={},
                            status="error",
                            error=load_err,
                        )
                        await session.commit()
                    continue

                all_handles: list[str] = []
                first_error: str | None = None
                for cls in classes:
                    validation_err = _validate_adapter_class(cls)
                    if validation_err:
                        first_error = first_error or validation_err
                        continue
                    conflict_err = registry._register_custom(cls, slug=slug, source="file")
                    if conflict_err:
                        first_error = first_error or conflict_err
                    else:
                        all_handles.extend(cls.handles)

                display = getattr(classes[0], "display_name", py_file.stem) if classes else py_file.stem
                schema = getattr(classes[0], "config_schema", {}) if classes else {}
                async with sessionmaker() as session:
                    await _upsert_adapter_row(
                        session,
                        slug=slug,
                        display_name=display,
                        version=None,
                        source="file",
                        entry_point=None,
                        filename=py_file.name,
                        handles=all_handles,
                        config_schema=schema,
                        status="error" if first_error else "loaded",
                        error=first_error,
                    )
                    await session.commit()

    logger.info("adapter registry built", extra={"handles": list(registry.all_handles())})
    return registry
```

- [ ] **Step 4: Run tests**

```bash
cd apps/api
uv run pytest tests/test_adapter_registry.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/ingestion/adapter_registry.py apps/api/tests/test_adapter_registry.py
git commit -m "feat(adapters): add AdapterRegistry with builtin, entrypoint, and file-drop discovery"
```

---

## Task 6: Wire Registry Into App and Worker

**Files:**
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/ingestion/tasks.py`
- Modify: `apps/api/app/ingestion/registry.py`

- [ ] **Step 1: Update `apps/api/app/main.py` lifespan to initialize registry**

In the `lifespan` function, after the `maybe_bootstrap_admin` call and before `yield`, add:

```python
from app.ingestion.adapter_registry import init_registry

# ... existing bootstrap call ...
async with get_sessionmaker()() as session:
    await maybe_bootstrap_admin(session, settings)

# Initialize adapter registry (discovers built-ins, entry points, file-drop).
await init_registry(get_sessionmaker())
```

Also add the import at the top of the lifespan function body (or at module level with other imports):
```python
from app.ingestion.adapter_registry import init_registry
```

- [ ] **Step 2: Update `apps/api/app/ingestion/tasks.py` to use registry**

Replace the static adapter block:

```python
# REMOVE these lines:
_GITHUB_ADAPTER = GitHubAdapter()
_WPORG_ADAPTER = WporgAdapter()
_WEBPAGE_ADAPTER = WebpageAdapter()
_REST_ADAPTER = RestEndpointAdapter()
_ADAPTERS: dict[str, SourceAdapter] = {
    **dict.fromkeys(_GITHUB_ADAPTER.handles, _GITHUB_ADAPTER),
    **dict.fromkeys(_WPORG_ADAPTER.handles, _WPORG_ADAPTER),
    **dict.fromkeys(_WEBPAGE_ADAPTER.handles, _WEBPAGE_ADAPTER),
    **dict.fromkeys(_REST_ADAPTER.handles, _REST_ADAPTER),
}

# REMOVE the resolve_adapter function:
def resolve_adapter(source_type: str) -> SourceAdapter:
    return _ADAPTERS[source_type]
```

Replace with:
```python
from celery.signals import worker_init

from app.ingestion.adapter_registry import get_registry, init_registry


@worker_init.connect
def _on_worker_init(**kwargs: object) -> None:
    """Initialize adapter registry when Celery worker process starts."""
    import asyncio
    asyncio.run(init_registry(get_worker_sessionmaker()))


def resolve_adapter(source_type: str) -> SourceAdapter:
    """Return adapter for source_type from the registry."""
    return get_registry().get(source_type)
```

Also remove these now-unused imports:
```python
# Remove:
from app.ingestion.adapters.github import GitHubAdapter
from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter
from app.ingestion.adapters.webpage import WebpageAdapter
from app.ingestion.adapters.wporg import WporgAdapter
```

- [ ] **Step 3: Update `apps/api/app/ingestion/registry.py` `add_source()` to use registry**

In `registry.py`, find the `add_source` function. Replace the `SOURCE_TYPES` check:

```python
# REMOVE:
from app.db.models import SOURCE_TYPES, Plugin, Source
# Change to:
from app.db.models import Plugin, Source

# In add_source(), replace:
if source_type not in SOURCE_TYPES:
    raise ValueError(f"unknown source_type: {source_type}")
# With:
from app.ingestion.adapter_registry import get_registry
try:
    registry = get_registry()
    if source_type not in registry.all_handles():
        raise ValueError(f"unknown source_type: {source_type!r} — not in registry")
except RuntimeError:
    pass  # Registry not initialized (e.g. in migration context) — skip validation
```

Also update the `SourceType` Literal and the `SourceSpec.source_type` field to accept any string:

```python
# Remove the SourceType Literal:
# SourceType = Literal["github_readme", ...]   <-- delete this

# Change SourceSpec:
class SourceSpec(BaseModel):
    source_type: str   # was: SourceType
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Verify the app starts correctly**

```bash
cd apps/api
uv run python -c "
from app.main import create_app
app = create_app()
print('app created ok')
"
```

Expected: `app created ok`

- [ ] **Step 5: Run existing ingestion tests to confirm nothing broke**

```bash
cd apps/api
uv run pytest tests/test_ingestion_tasks.py tests/test_registry_config.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/main.py apps/api/app/ingestion/tasks.py apps/api/app/ingestion/registry.py
git commit -m "feat(startup): wire AdapterRegistry into FastAPI lifespan and Celery worker_init"
```

---

## Task 7: API Schemas

**Files:**
- Modify: `apps/api/app/api/schemas.py`

`AdapterTypeInfo` is already defined in `adapter_registry.py` (used internally by the registry). Only `AdapterPluginSummary` needs to be added to `schemas.py`. Routes import `AdapterTypeInfo` directly from `adapter_registry`, not from `schemas`.

- [ ] **Step 1: Add `AdapterPluginSummary` to `apps/api/app/api/schemas.py`**

Add near the end of the file (after existing source-related schemas):

```python
class AdapterPluginSummary(BaseModel):
    """Metadata row for one installed adapter."""

    slug: str
    display_name: str
    version: str | None
    source: str
    handles: list[str]
    config_schema: dict[str, Any]
    status: str
    error: str | None
    installed_at: str

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Verify import**

```bash
cd apps/api
python -c "from app.api.schemas import AdapterPluginSummary; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/api/schemas.py
git commit -m "feat(schemas): add AdapterPluginSummary schema"
```

---

## Task 8: API Routes — /adapter-plugins

**Files:**
- Create: `apps/api/app/api/routes_adapters.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write failing route tests first**

Create `apps/api/tests/test_routes_adapters.py`:

```python
"""Tests for /api/v1/admin/adapter-plugins routes."""
from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import UserClaims, create_access_token
from app.config import Settings, get_settings
from app.main import create_app

_JWT_SECRET = "test-jwt-secret"  # noqa: S105


def _test_settings(**kwargs: Any) -> Settings:
    return Settings(jwt_secret=_JWT_SECRET, bootstrap_email=None, bootstrap_password=None, **kwargs)


def _admin_cookie() -> dict[str, str]:
    claims = UserClaims(
        sub=str(uuid.uuid4()),
        email="admin@test.com",
        permissions=["sources:read", "sources:write"],
        roles=[],
    )
    token = create_access_token(claims, secret=_JWT_SECRET, ttl_seconds=900)
    return {"access_token": token}


def _make_client(*, custom_adapters_dir: str = "") -> TestClient:
    """Create a test client with a mocked adapter registry."""
    from app.api.deps import get_settings_dep

    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _test_settings(
        custom_adapters_dir=custom_adapters_dir
    )

    mock_registry = MagicMock()
    mock_registry.types_with_schema.return_value = []
    mock_registry.all_handles.return_value = frozenset()

    with patch("app.ingestion.adapter_registry._registry", mock_registry):
        with patch("app.ingestion.adapter_registry.init_registry", new=AsyncMock(return_value=mock_registry)):
            with TestClient(app) as client:
                return client


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield _make_client()


def test_list_adapter_plugins_returns_200(client: TestClient):
    with patch("app.api.routes_adapters.get_adapter_plugin_rows", new=AsyncMock(return_value=[])):
        resp = client.get(
            "/api/v1/admin/adapter-plugins",
            cookies=_admin_cookie(),
        )
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_adapter_types_returns_200(client: TestClient):
    from app.ingestion.adapter_registry import AdapterTypeInfo

    fake_types = [
        AdapterTypeInfo(
            source_type="test_type",
            display_name="Test",
            adapter_slug="builtin.test",
            config_schema={},
            is_builtin=True,
            multi_instance=False,
        )
    ]
    with patch("app.api.routes_adapters._get_registry_or_404") as mock_reg:
        mock_reg.return_value = MagicMock(types_with_schema=lambda: fake_types)
        resp = client.get(
            "/api/v1/admin/adapter-plugins/types",
            cookies=_admin_cookie(),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source_type"] == "test_type"


def test_upload_adapter_rejects_non_py(client: TestClient, tmp_path):
    fake_file = io.BytesIO(b"not python")
    resp = client.post(
        "/api/v1/admin/adapter-plugins/upload",
        cookies=_admin_cookie(),
        files={"file": ("bad.txt", fake_file, "text/plain")},
    )
    assert resp.status_code == 422


def test_delete_builtin_is_403(client: TestClient):
    from app.db.models import AdapterPlugin
    from datetime import datetime, timezone

    fake_row = MagicMock(spec=AdapterPlugin)
    fake_row.slug = "builtin.github"
    fake_row.source = "builtin"

    with patch("app.api.routes_adapters._get_adapter_row_or_404", new=AsyncMock(return_value=fake_row)):
        resp = client.delete(
            "/api/v1/admin/adapter-plugins/builtin.github",
            cookies=_admin_cookie(),
        )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to confirm they fail (route file missing)**

```bash
cd apps/api
uv run pytest tests/test_routes_adapters.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.api.routes_adapters'` or import error.

- [ ] **Step 3: Create `apps/api/app/api/routes_adapters.py`**

```python
"""Adapter plugin management routes (GET/POST/DELETE /adapter-plugins).

Author: Al Amin Ahamed.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings_dep, require_permission
from app.api.schemas import AdapterPluginSummary
from app.config import Settings
from app.db.engine import get_session
from app.db.models import AdapterPlugin
from app.ingestion.adapter_registry import (
    AdapterRegistry,
    AdapterTypeInfo,
    _load_adapter_classes_from_file,
    _upsert_adapter_row,
    _validate_adapter_class,
    get_registry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/adapter-plugins", tags=["adapters"])


def _row_to_summary(row: AdapterPlugin) -> AdapterPluginSummary:
    return AdapterPluginSummary(
        slug=row.slug,
        display_name=row.display_name,
        version=row.version,
        source=row.source,
        handles=row.handles,
        config_schema=row.config_schema,
        status=row.status,
        error=row.error,
        installed_at=row.installed_at.isoformat() if row.installed_at else "",
    )


async def get_adapter_plugin_rows(session: AsyncSession) -> list[AdapterPlugin]:
    result = await session.execute(select(AdapterPlugin).order_by(AdapterPlugin.slug))
    return list(result.scalars().all())


async def _get_adapter_row_or_404(session: AsyncSession, slug: str) -> AdapterPlugin:
    result = await session.execute(
        select(AdapterPlugin).where(AdapterPlugin.slug == slug)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="adapter not found")
    return row


def _get_registry_or_404() -> AdapterRegistry:
    try:
        return get_registry()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("", response_model=list[AdapterPluginSummary])
async def list_adapter_plugins(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_permission("sources:read")),
) -> list[AdapterPluginSummary]:
    """List all installed adapters (builtin + entrypoint + file)."""
    rows = await get_adapter_plugin_rows(session)
    return [_row_to_summary(r) for r in rows]


@router.get("/types", response_model=list[AdapterTypeInfo])
async def list_adapter_types(
    _: None = Depends(require_permission("sources:read")),
) -> list[AdapterTypeInfo]:
    """Return available source types with config schemas for AddSourceModal."""
    registry = _get_registry_or_404()
    return registry.types_with_schema()


@router.post("/upload", response_model=AdapterPluginSummary)
async def upload_adapter_plugin(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: None = Depends(require_permission("sources:write")),
) -> AdapterPluginSummary:
    """Upload a .py adapter file. Validates immediately; returns status."""
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .py files are accepted",
        )

    adapters_dir = settings.custom_adapters_dir
    if not adapters_dir:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File-drop adapter directory not configured (CUSTOM_ADAPTERS_DIR is empty)",
        )

    target_dir = Path(adapters_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file.filename
    slug = f"file.{target_path.stem}"

    content = await file.read()
    target_path.write_bytes(content)

    classes, load_err = _load_adapter_classes_from_file(target_path)

    registry = _get_registry_or_404()
    final_status = "loaded"
    final_error: str | None = None
    all_handles: list[str] = []

    if load_err:
        final_status = "error"
        final_error = load_err
    else:
        for cls in classes:
            validation_err = _validate_adapter_class(cls)
            if validation_err:
                final_status = "error"
                final_error = final_error or validation_err
                continue
            # Check for conflicts with existing loaded adapters
            conflicts = [h for h in cls.handles if h in registry.all_handles()]
            if conflicts:
                final_status = "error"
                final_error = final_error or f"conflicts with existing type(s): {', '.join(conflicts)}"
            else:
                all_handles.extend(cls.handles)

        if final_status == "loaded" and not all_handles:
            final_status = "error"
            final_error = "no valid adapter classes found"

    display = getattr(classes[0], "display_name", target_path.stem) if classes else target_path.stem
    schema = getattr(classes[0], "config_schema", {}) if classes else {}

    await _upsert_adapter_row(
        session,
        slug=slug,
        display_name=display,
        version=None,
        source="file",
        entry_point=None,
        filename=file.filename,
        handles=all_handles,
        config_schema=schema,
        status=final_status,
        error=final_error,
    )
    await session.commit()

    row = await _get_adapter_row_or_404(session, slug)
    return _row_to_summary(row)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_adapter_plugin(
    slug: str,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
    _: None = Depends(require_permission("sources:write")),
) -> None:
    """Delete a file-based adapter. Returns 403 for builtin/entrypoint adapters."""
    row = await _get_adapter_row_or_404(session, slug)

    if row.source != "file":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only file-based adapters can be deleted via the API",
        )

    if row.filename and settings.custom_adapters_dir:
        file_path = Path(settings.custom_adapters_dir) / row.filename
        if file_path.exists():
            file_path.unlink()

    await session.delete(row)
    await session.commit()
```

- [ ] **Step 4: Wire the adapters router into `apps/api/app/main.py`**

Add import and include_router:

```python
# At top with other route imports:
from app.api import routes_adapters

# In create_app(), with other include_router calls:
app.include_router(routes_adapters.router)
```

- [ ] **Step 5: Run route tests**

```bash
cd apps/api
uv run pytest tests/test_routes_adapters.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/routes_adapters.py apps/api/app/main.py apps/api/tests/test_routes_adapters.py
git commit -m "feat(api): add /adapter-plugins routes — list, types, upload, delete"
```

---

## Task 9: Docker Compose — custom_adapters Volume

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add volume mount to `app` and `worker` services**

In `docker-compose.yml`, under the `app:` service definition, add:
```yaml
    volumes:
      - custom_adapters:/app/custom_adapters
```

Under the `worker:` service definition, add the same:
```yaml
    volumes:
      - custom_adapters:/app/custom_adapters
```

At the bottom `volumes:` section, add:
```yaml
  custom_adapters:
```

- [ ] **Step 2: Verify compose file is valid**

```bash
docker compose config --quiet && echo "config valid"
```

Expected: `config valid`

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(infra): add custom_adapters shared volume for app and worker"
```

---

## Task 10: Frontend Types and API Functions

**Files:**
- Modify: `apps/admin/src/types/api.ts`
- Modify: `apps/admin/src/api/admin.ts`

- [ ] **Step 1: Add interfaces to `apps/admin/src/types/api.ts`**

Add after the existing `SourceSummary` interface:

```ts
export interface AdapterTypeInfo {
  source_type: string
  display_name: string
  adapter_slug: string
  config_schema: Record<string, unknown>
  is_builtin: boolean
  multi_instance: boolean
}

export interface AdapterPluginSummary {
  slug: string
  display_name: string
  version: string | null
  source: "builtin" | "entrypoint" | "file"
  handles: string[]
  config_schema: Record<string, unknown>
  status: "loaded" | "error" | "disabled"
  error: string | null
  installed_at: string
}
```

- [ ] **Step 2: Add API functions to `apps/admin/src/api/admin.ts`**

Add after the `patchSourceConfig` function:

```ts
export async function getAdapterTypes(): Promise<AdapterTypeInfo[]> {
  const res = await apiClient.get<AdapterTypeInfo[]>("/api/v1/admin/adapter-plugins/types");
  return res.data;
}

export async function listAdapterPlugins(): Promise<AdapterPluginSummary[]> {
  const res = await apiClient.get<AdapterPluginSummary[]>("/api/v1/admin/adapter-plugins");
  return res.data;
}

export async function uploadAdapterPlugin(file: File): Promise<AdapterPluginSummary> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiClient.post<AdapterPluginSummary>(
    "/api/v1/admin/adapter-plugins/upload",
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

export async function deleteAdapterPlugin(slug: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/adapter-plugins/${encodeURIComponent(slug)}`);
}
```

Also add the new types to the import at the top of `admin.ts`:
```ts
import type {
  AdapterPluginSummary,
  AdapterTypeInfo,
  // ... existing imports ...
} from "@/types/api";
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd apps/admin
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/admin/src/types/api.ts apps/admin/src/api/admin.ts
git commit -m "feat(frontend): add AdapterTypeInfo, AdapterPluginSummary types and API functions"
```

---

## Task 11: JsonSchemaForm Component

**Files:**
- Create: `apps/admin/src/components/JsonSchemaForm.tsx`

- [ ] **Step 1: Create `apps/admin/src/components/JsonSchemaForm.tsx`**

```tsx
// Dynamic form rendered from a JSON Schema properties object. Author: Al Amin Ahamed.
import { useState } from "react";

interface PropertySchema {
  type?: string;
  title?: string;
  description?: string;
  format?: string;
  enum?: string[];
}

interface JsonSchemaFormProps {
  schema: Record<string, unknown>;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
}

const inputBase =
  "w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

function FieldInput({
  name,
  prop,
  required,
  value,
  onChange,
}: {
  name: string;
  prop: PropertySchema;
  required: boolean;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = prop.title ?? name;
  const type = prop.type ?? "string";

  let input: React.ReactNode;

  if (prop.enum && prop.enum.length > 0) {
    input = (
      <select
        className={inputBase}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      >
        {!required && <option value="">— select —</option>}
        {prop.enum.map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  } else if (type === "boolean") {
    const checked = Boolean(value);
    input = (
      <button
        type="button"
        onClick={() => onChange(!checked)}
        aria-checked={checked}
        className={`relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${checked ? "bg-success" : "bg-muted-foreground/40"}`}
      >
        <span
          className={`pointer-events-none block h-3 w-3 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-3" : "translate-x-0"}`}
        />
      </button>
    );
  } else if (type === "integer" || type === "number") {
    input = (
      <input
        type="number"
        className={inputBase}
        value={String(value ?? "")}
        onChange={(e) => onChange(type === "integer" ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
      />
    );
  } else if (prop.format === "password") {
    input = (
      <input
        type="password"
        className={inputBase}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  } else if (prop.format === "uri") {
    input = (
      <input
        type="url"
        className={inputBase}
        placeholder="https://..."
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  } else {
    input = (
      <input
        type="text"
        className={inputBase}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div>
      <label className="block text-xs font-medium mb-1">
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {input}
      {prop.description && (
        <p className="mt-0.5 text-[11px] text-muted-foreground">{prop.description}</p>
      )}
    </div>
  );
}

export function JsonSchemaForm({ schema, value, onChange }: JsonSchemaFormProps) {
  const properties = (schema as { properties?: Record<string, PropertySchema> }).properties;
  const required: string[] = (schema as { required?: string[] }).required ?? [];

  // Empty or missing schema — fall back to raw JSON textarea.
  if (!properties || Object.keys(properties).length === 0) {
    const [raw, setRaw] = useState(() => {
      try { return JSON.stringify(value, null, 2); } catch { return "{}"; }
    });
    const [parseErr, setParseErr] = useState<string | null>(null);

    return (
      <div>
        <label className="block text-xs font-medium mb-1">Config (JSON)</label>
        <textarea
          className={`${inputBase} font-mono text-xs min-h-[120px]`}
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            try {
              onChange(JSON.parse(e.target.value));
              setParseErr(null);
            } catch {
              setParseErr("Invalid JSON");
            }
          }}
        />
        {parseErr && <p className="mt-0.5 text-[11px] text-destructive">{parseErr}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {Object.entries(properties).map(([key, prop]) => (
        <FieldInput
          key={key}
          name={key}
          prop={prop}
          required={required.includes(key)}
          value={value[key]}
          onChange={(v) => onChange({ ...value, [key]: v })}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd apps/admin
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/src/components/JsonSchemaForm.tsx
git commit -m "feat(ui): add JsonSchemaForm component for dynamic adapter config fields"
```

---

## Task 12: AdaptersPage — Admin Page

**Files:**
- Create: `apps/admin/src/pages/AdaptersPage.tsx`
- Modify: `apps/admin/src/app/routes.tsx`
- Modify: `apps/admin/src/components/layout/AppShell.tsx`

- [ ] **Step 1: Create `apps/admin/src/pages/AdaptersPage.tsx`**

```tsx
// Adapter plugin management page. Author: Al Amin Ahamed.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteAdapterPlugin,
  listAdapterPlugins,
  uploadAdapterPlugin,
} from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { AdapterPluginSummary } from "@/types/api";

const STATUS_CFG: Record<string, { cls: string; label: string }> = {
  loaded:   { cls: "bg-success/10 text-success border-success/20",           label: "Loaded"   },
  error:    { cls: "bg-destructive/10 text-destructive border-destructive/20", label: "Error"    },
  disabled: { cls: "bg-muted text-muted-foreground border-border",            label: "Disabled" },
};

const SOURCE_CFG: Record<string, { label: string; icon: string }> = {
  builtin:    { label: "Built-in",    icon: "ti-package" },
  entrypoint: { label: "pip package", icon: "ti-box"     },
  file:       { label: "Uploaded",    icon: "ti-file-upload" },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CFG[status] ?? STATUS_CFG.disabled;
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", cfg.cls)}>
      {cfg.label}
    </span>
  );
}

function AdapterRow({ row }: { row: AdapterPluginSummary }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteAdapterPlugin(row.slug),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adapter-plugins"] });
      toast.ok(`Adapter "${row.display_name}" removed`);
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const src = SOURCE_CFG[row.source] ?? SOURCE_CFG.file;

  return (
    <tr className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors">
      {/* Name */}
      <td className="py-2.5 pl-4 pr-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-[12px] font-medium text-foreground">{row.display_name}</span>
          <span className="font-mono text-[10px] text-muted-foreground">{row.slug}</span>
        </div>
      </td>

      {/* Handles */}
      <td className="pr-3">
        <div className="flex flex-wrap gap-1">
          {row.handles.length === 0 ? (
            <span className="text-[11px] text-muted-foreground">—</span>
          ) : (
            row.handles.map((h) => (
              <Badge key={h} variant="secondary" className="font-mono text-[10px]">{h}</Badge>
            ))
          )}
        </div>
      </td>

      {/* Source */}
      <td className="pr-3 text-[12px] text-muted-foreground whitespace-nowrap">
        <span className="inline-flex items-center gap-1">
          <i className={`ti ${src.icon} text-[11px]`} />
          {src.label}
        </span>
      </td>

      {/* Version */}
      <td className="pr-3 text-[12px] text-muted-foreground">
        {row.version ?? <span className="text-muted-foreground/50">—</span>}
      </td>

      {/* Status */}
      <td className="pr-3">
        <div className="flex flex-col gap-0.5">
          <StatusBadge status={row.status} />
          {row.error && (
            <p className="max-w-[220px] truncate text-[10px] text-destructive" title={row.error}>
              {row.error}
            </p>
          )}
        </div>
      </td>

      {/* Actions */}
      <td className="pr-3 text-right">
        {row.source === "file" && (
          confirmDelete ? (
            <span className="inline-flex items-center gap-1.5 text-[11px]">
              <span className="text-destructive font-medium">Delete?</span>
              <button
                type="button"
                onClick={() => { deleteMutation.mutate(); setConfirmDelete(false); }}
                disabled={deleteMutation.isPending}
                className="text-destructive font-semibold hover:underline disabled:opacity-50"
              >
                Yes
              </button>
              <button type="button" onClick={() => setConfirmDelete(false)} className="text-muted-foreground hover:underline">
                No
              </button>
            </span>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setConfirmDelete(true)}
              title="Remove adapter"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            >
              <i className="ti ti-trash text-[12px]" />
            </Button>
          )
        )}
      </td>
    </tr>
  );
}

export function AdaptersPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["adapter-plugins"],
    queryFn: listAdapterPlugins,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadAdapterPlugin(file),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["adapter-plugins"] });
      if (result.status === "error") {
        toast.err(`Adapter uploaded but has errors: ${result.error}`);
      } else {
        toast.ok(`Adapter "${result.display_name}" uploaded — restart required to activate`);
      }
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) uploadMutation.mutate(file);
    e.target.value = "";
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Adapter Plugins</h1>
          <p className="text-sm text-muted-foreground">
            Installed ingestion adapters. Restart required to activate uploaded adapters.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".py"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button
            size="sm"
            onClick={() => fileRef.current?.click()}
            disabled={uploadMutation.isPending}
          >
            <i className="ti ti-upload text-[12px] mr-1.5" />
            {uploadMutation.isPending ? "Uploading…" : "Upload Adapter"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        <ErrorState message={extractErrorMessage(error)} />
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60 bg-muted/30 text-left text-[11px] font-medium text-muted-foreground">
                <th className="py-2 pl-4 pr-3 font-medium">Adapter</th>
                <th className="py-2 pr-3 font-medium">Handles</th>
                <th className="py-2 pr-3 font-medium">Source</th>
                <th className="py-2 pr-3 font-medium">Version</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data!.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-[12px] text-muted-foreground">
                    No adapters found. Run the app once to register built-ins.
                  </td>
                </tr>
              ) : (
                data!.map((row) => <AdapterRow key={row.slug} row={row} />)
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add route to `apps/admin/src/app/routes.tsx`**

Add import:
```ts
import { AdaptersPage } from "@/pages/AdaptersPage";
```

Add route inside the `ProtectedShell` children array (after `users` route):
```ts
{ path: "adapters", element: <AdaptersPage /> },
```

- [ ] **Step 3: Add nav entry to `apps/admin/src/components/layout/AppShell.tsx`**

In the `NAV` array, add after the `users` entry:
```ts
{ to: "/adapters", label: "Adapters", icon: "ti-plug-connected", permission: "sources:read" },
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd apps/admin
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/pages/AdaptersPage.tsx apps/admin/src/app/routes.tsx apps/admin/src/components/layout/AppShell.tsx
git commit -m "feat(ui): add AdaptersPage with upload, list, and delete functionality"
```

---

## Task 13: Update AddSourceModal — API-Driven Types

**Files:**
- Modify: `apps/admin/src/features/AddSourceModal.tsx`

- [ ] **Step 1: Replace the AddSourceModal with the updated version**

Replace the entire file `apps/admin/src/features/AddSourceModal.tsx`:

```tsx
// Two-step add-source modal: type picker → config form. Author: Al Amin Ahamed.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addSource, getAdapterTypes } from "@/api/admin";
import { Button } from "@/components/ui/button";
import { JsonSchemaForm } from "@/components/JsonSchemaForm";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ToastProvider";
import { extractErrorMessage } from "@/lib/queryClient";
import type { AdapterTypeInfo } from "@/types/api";

const TYPE_ICONS: Record<string, string> = {
  github_readme:    "ti-brand-github",
  github_changelog: "ti-file-text",
  github_docs:      "ti-book",
  github_issues:    "ti-message-circle",
  wporg_faq:        "ti-help-circle",
  wporg_changelog:  "ti-clock",
  wporg_support:    "ti-messages",
  webpage:          "ti-world",
  rest_endpoint:    "ti-api",
};

// ── Built-in specialized config forms (unchanged from before) ─────────────────

interface WebpageConfig {
  url: string; name: string; max_depth: number; selector: string; url_filter: string;
}
interface RestConfig {
  url: string; name: string; method: "GET" | "POST";
  auth_type: "none" | "bearer" | "api_key";
  bearer_token: string; api_key_header: string; api_key_value: string;
  content_field: string; title_field: string; url_field: string; id_field: string;
  pagination: "none" | "page_param" | "link_header" | "cursor";
  page_param: string; page_size_param: string; page_size: number;
  cursor_field: string; items_path: string;
}
const DEFAULT_WEBPAGE: WebpageConfig = { url: "", name: "", max_depth: 2, selector: "", url_filter: "" };
const DEFAULT_REST: RestConfig = {
  url: "", name: "", method: "GET", auth_type: "none",
  bearer_token: "", api_key_header: "", api_key_value: "",
  content_field: "", title_field: "", url_field: "", id_field: "",
  pagination: "none", page_param: "page", page_size_param: "per_page",
  page_size: 100, cursor_field: "", items_path: "",
};

const inputBase = "w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

function buildHeaders(cfg: RestConfig): Record<string, string> {
  if (cfg.auth_type === "bearer") return { Authorization: `Bearer ${cfg.bearer_token}` };
  if (cfg.auth_type === "api_key") return { [cfg.api_key_header]: cfg.api_key_value };
  return {};
}

function buildRestConfig(cfg: RestConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {
    url: cfg.url, method: cfg.method, content_field: cfg.content_field,
    id_field: cfg.id_field, pagination: cfg.pagination,
  };
  const headers = buildHeaders(cfg);
  if (Object.keys(headers).length) out.headers = headers;
  if (cfg.title_field) out.title_field = cfg.title_field;
  if (cfg.url_field) out.url_field = cfg.url_field;
  if (cfg.items_path) out.items_path = cfg.items_path;
  if (cfg.pagination === "page_param") {
    out.page_param = cfg.page_param;
    out.page_size_param = cfg.page_size_param;
    out.page_size = cfg.page_size;
  }
  if (cfg.pagination === "cursor") out.cursor_field = cfg.cursor_field;
  return out;
}

function WebpageConfigForm({ cfg, setCfg }: { cfg: WebpageConfig; setCfg: (c: WebpageConfig) => void }) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input className={inputBase} placeholder="e.g. Plugin Docs Site" value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Start URL <span className="text-destructive">*</span></label>
        <input type="url" className={inputBase} placeholder="https://..." value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value, name: cfg.name || new URL(e.target.value.startsWith("http") ? e.target.value : `https://${e.target.value}`).hostname })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Max depth <span className="text-muted-foreground text-[10px]">(1–5)</span></label>
        <input type="range" min={1} max={5} value={cfg.max_depth}
          onChange={(e) => setCfg({ ...cfg, max_depth: Number(e.target.value) })}
          className="w-full accent-primary" />
        <span className="text-[11px] text-muted-foreground">{cfg.max_depth}</span>
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">CSS selector <span className="text-muted-foreground text-[10px]">(optional)</span></label>
        <input className={inputBase} placeholder="main, article, .content" value={cfg.selector}
          onChange={(e) => setCfg({ ...cfg, selector: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">URL filter regex <span className="text-muted-foreground text-[10px]">(optional)</span></label>
        <input className={`${inputBase} font-mono`} placeholder="/docs/.*" value={cfg.url_filter}
          onChange={(e) => setCfg({ ...cfg, url_filter: e.target.value })} />
      </div>
    </div>
  );
}

function RestConfigForm({ cfg, setCfg }: { cfg: RestConfig; setCfg: (c: RestConfig) => void }) {
  return (
    <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input className={inputBase} placeholder="e.g. My REST API" value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">URL <span className="text-destructive">*</span></label>
        <input type="url" className={inputBase} placeholder="https://api.example.com/items" value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Content field <span className="text-destructive">*</span></label>
        <input className={`${inputBase} font-mono`} placeholder="body" value={cfg.content_field}
          onChange={(e) => setCfg({ ...cfg, content_field: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">ID field <span className="text-destructive">*</span></label>
        <input className={`${inputBase} font-mono`} placeholder="id" value={cfg.id_field}
          onChange={(e) => setCfg({ ...cfg, id_field: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Pagination</label>
        <select className={inputBase} value={cfg.pagination}
          onChange={(e) => setCfg({ ...cfg, pagination: e.target.value as RestConfig["pagination"] })}>
          <option value="none">None</option>
          <option value="page_param">Page parameter</option>
          <option value="link_header">Link header (RFC 5988)</option>
          <option value="cursor">Cursor</option>
        </select>
      </div>
      {cfg.pagination === "page_param" && (
        <>
          <div>
            <label className="block text-xs font-medium mb-1">Page param</label>
            <input className={`${inputBase} font-mono`} value={cfg.page_param}
              onChange={(e) => setCfg({ ...cfg, page_param: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Page size param</label>
            <input className={`${inputBase} font-mono`} value={cfg.page_size_param}
              onChange={(e) => setCfg({ ...cfg, page_size_param: e.target.value })} />
          </div>
        </>
      )}
      {cfg.pagination === "cursor" && (
        <div>
          <label className="block text-xs font-medium mb-1">Cursor field</label>
          <input className={`${inputBase} font-mono`} value={cfg.cursor_field}
            onChange={(e) => setCfg({ ...cfg, cursor_field: e.target.value })} />
        </div>
      )}
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export function AddSourceModal({
  slug,
  usedTypes,
  onClose,
}: {
  slug: string;
  usedTypes: Set<string>;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [step, setStep] = useState<"pick" | "configure">("pick");
  const [selectedType, setSelectedType] = useState<string>("");
  const [webCfg, setWebCfg] = useState<WebpageConfig>(DEFAULT_WEBPAGE);
  const [restCfg, setRestCfg] = useState<RestConfig>(DEFAULT_REST);
  const [customConfig, setCustomConfig] = useState<Record<string, unknown>>({});

  const { data: adapterTypes, isLoading: typesLoading } = useQuery({
    queryKey: ["adapter-types"],
    queryFn: getAdapterTypes,
    staleTime: 60_000,
  });

  const mutation = useMutation({
    mutationFn: ({ type, name, config }: { type: string; name: string; config: Record<string, unknown> }) =>
      addSource(slug, type, name, config),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["sources", slug] });
      qc.invalidateQueries({ queryKey: ["plugins"] });
      toast.ok(`Added source "${data.name}"`);
      onClose();
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const types = adapterTypes ?? [];
  const singleTypes = types.filter((t) => !t.multi_instance && !usedTypes.has(t.source_type));
  const multiTypes = types.filter((t) => t.multi_instance);

  const selectedTypeInfo = types.find((t) => t.source_type === selectedType);

  function handlePickType(typeInfo: AdapterTypeInfo) {
    if (typeInfo.multi_instance) {
      setSelectedType(typeInfo.source_type);
      setCustomConfig({});
      setStep("configure");
    } else {
      mutation.mutate({ type: typeInfo.source_type, name: typeInfo.source_type, config: {} });
    }
  }

  function handleSubmitConfig() {
    if (selectedType === "webpage") {
      mutation.mutate({
        type: "webpage",
        name: webCfg.name,
        config: {
          url: webCfg.url,
          max_depth: webCfg.max_depth,
          ...(webCfg.selector ? { selector: webCfg.selector } : {}),
          ...(webCfg.url_filter ? { url_filter: webCfg.url_filter } : {}),
        },
      });
    } else if (selectedType === "rest_endpoint") {
      mutation.mutate({ type: "rest_endpoint", name: restCfg.name, config: buildRestConfig(restCfg) });
    } else {
      // Custom adapter type — use name from customConfig or fall back to type
      const name = String(customConfig.name ?? selectedType);
      mutation.mutate({ type: selectedType, name, config: customConfig });
    }
  }

  const configValid =
    selectedType === "webpage"
      ? webCfg.url.trim() !== "" && webCfg.name.trim() !== ""
      : selectedType === "rest_endpoint"
      ? restCfg.url.trim() !== "" && restCfg.name.trim() !== "" &&
        restCfg.content_field.trim() !== "" && restCfg.id_field.trim() !== ""
      : true; // Custom types: always allow submit (schema required fields enforced by backend)

  const configTitle = selectedTypeInfo?.display_name ?? selectedType.replace(/_/g, " ");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-background border border-border rounded-xl shadow-xl w-full max-w-lg mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {step === "pick" ? "Add source" : `Configure ${configTitle}`}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <i className="ti ti-x text-sm" />
          </button>
        </div>

        <div className="p-5">
          {step === "pick" ? (
            typesLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : (
              <div className="space-y-4">
                {singleTypes.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-2">GitHub &amp; WordPress.org</p>
                    <div className="grid grid-cols-2 gap-2">
                      {singleTypes.map((t) => (
                        <button
                          key={t.source_type}
                          onClick={() => handlePickType(t)}
                          disabled={mutation.isPending}
                          className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors disabled:opacity-50"
                        >
                          <i className={`ti ${TYPE_ICONS[t.source_type] ?? "ti-file"} text-muted-foreground`} />
                          <span className="font-mono text-[12px]">{t.source_type}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {multiTypes.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-muted-foreground mb-2">Configurable sources (multiple allowed)</p>
                    <div className="grid grid-cols-2 gap-2">
                      {multiTypes.map((t) => (
                        <button
                          key={t.source_type}
                          onClick={() => handlePickType(t)}
                          className="flex flex-col items-start gap-0.5 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors"
                        >
                          <span className="flex items-center gap-1.5">
                            <i className={`ti ${TYPE_ICONS[t.source_type] ?? "ti-plug-connected"} text-muted-foreground text-[12px]`} />
                            <span className="text-[12px] font-medium">{t.display_name}</span>
                          </span>
                          {!t.is_builtin && (
                            <span className="font-mono text-[10px] text-muted-foreground">{t.source_type}</span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {types.length === 0 && (
                  <p className="text-sm text-muted-foreground">No adapter types available.</p>
                )}
              </div>
            )
          ) : (
            <div className="space-y-4">
              {selectedType === "webpage" ? (
                <WebpageConfigForm cfg={webCfg} setCfg={setWebCfg} />
              ) : selectedType === "rest_endpoint" ? (
                <RestConfigForm cfg={restCfg} setCfg={setRestCfg} />
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
                    <input
                      className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      placeholder={`e.g. My ${configTitle} source`}
                      value={String(customConfig.name ?? "")}
                      onChange={(e) => setCustomConfig({ ...customConfig, name: e.target.value })}
                    />
                  </div>
                  <JsonSchemaForm
                    schema={(selectedTypeInfo?.config_schema as Record<string, unknown>) ?? {}}
                    value={customConfig}
                    onChange={setCustomConfig}
                  />
                </div>
              )}
              <div className="flex justify-between pt-1">
                <Button variant="ghost" size="sm" onClick={() => setStep("pick")}>← Back</Button>
                <Button size="sm" onClick={handleSubmitConfig} disabled={!configValid || mutation.isPending}>
                  {mutation.isPending ? "Adding…" : "Add source"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd apps/admin
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/src/features/AddSourceModal.tsx
git commit -m "feat(ui): AddSourceModal uses API-driven adapter types, renders JsonSchemaForm for custom types"
```

---

## Task 14: Rebuild and Smoke Test

**Files:** none (infra only)

- [ ] **Step 1: Rebuild app and worker containers**

```bash
docker compose build app worker
```

Expected: both build successfully.

- [ ] **Step 2: Run all adapter and registry tests**

```bash
cd apps/api
uv run pytest tests/test_adapter_registry.py tests/test_routes_adapters.py tests/test_webpage_adapter.py tests/test_rest_endpoint_adapter.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Start containers and check registry initializes**

```bash
docker compose up -d app worker
docker compose logs app --tail=30 | grep -i "adapter registry"
```

Expected: log line like `adapter registry built` with handles list.

- [ ] **Step 4: Verify adapter_plugins rows in DB**

```bash
docker compose exec postgres psql -U wprag -d wprag -c "SELECT slug, status, handles FROM adapter_plugins ORDER BY slug;"
```

Expected: 4 rows for builtin.github, builtin.rest_endpoint, builtin.webpage, builtin.wporg — all `loaded`.

- [ ] **Step 5: Rebuild and start admin frontend**

```bash
docker compose build admin && docker compose up -d admin
curl -s -o /dev/null -w "%{http_code}" http://localhost:8081
```

Expected: `200`

- [ ] **Step 6: Test adapter types API**

```bash
# Get an access token first by logging into the admin UI at http://localhost:8081
# Then test the types endpoint (or check via browser devtools):
curl -s http://localhost:8000/api/v1/admin/adapter-plugins/types -b "access_token=<token>" | python3 -m json.tool | head -20
```

Expected: JSON array with 9+ source type entries (7 github/wporg + webpage + rest_endpoint).

- [ ] **Step 7: Final commit if any infra changes made**

```bash
git add -A
git status
# Only commit if there are actual changes
```

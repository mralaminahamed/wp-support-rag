# Webpage & REST Endpoint Source Types — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `webpage` (configurable-depth crawler) and `rest_endpoint` (paginated JSON API) source types, with multi-instance support per plugin and a config-form UI.

**Architecture:** Drop the `UNIQUE(plugin_id, source_type)` constraint in favour of `UNIQUE(plugin_id, name)`, letting plugins have multiple sources of the same type. Two new adapters implement the `SourceAdapter` protocol. Route params switch from `source_type` to `source_id` for patch/delete/ingest-single. The frontend gains a two-step add-source modal with type-specific config forms.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, BeautifulSoup4/lxml, httpx, React 18, TanStack Query, TypeScript.

---

## File Map

### Created
| File | Responsibility |
|------|---------------|
| `apps/api/app/ingestion/adapters/webpage.py` | WebpageAdapter — BFS crawler |
| `apps/api/app/ingestion/adapters/rest_endpoint.py` | RestEndpointAdapter — paginated JSON API |
| `apps/api/app/db/migrations/versions/20260603_0010_webpage_rest_sources.py` | DB migration |
| `apps/admin/src/features/AddSourceModal.tsx` | Two-step add-source modal (type picker + config forms) |

### Modified
| File | Change |
|------|--------|
| `apps/api/pyproject.toml` | Add beautifulsoup4, lxml |
| `apps/api/app/db/models.py` | Add `name` to Source; expand SOURCE_TYPES |
| `apps/api/app/api/schemas.py` | Add `name` to SourceSummary; update AddSourceRequest; add PatchConfigRequest |
| `apps/api/app/api/routes_admin.py` | Switch patch/delete/ingest-single to use source_id; add config-patch route; update add-source validation |
| `apps/api/app/ingestion/tasks.py` | Register WebpageAdapter + RestEndpointAdapter |
| `apps/admin/src/types/api.ts` | Add `name`; expand SOURCE_TYPES |
| `apps/admin/src/api/admin.ts` | Switch to source_id params; add patchSourceConfig |
| `apps/admin/src/features/SourcesRow.tsx` | Show name; use source_id; add edit-config button; delegate add to modal |

---

## Task 1: DB Migration — name column + constraint swap + new source types

**Files:**
- Create: `apps/api/app/db/migrations/versions/20260603_0010_webpage_rest_sources.py`

- [ ] **Step 1: Write the migration**

```python
"""Add Source.name, drop unique(plugin_id, source_type), add unique(plugin_id, name), extend source_type check.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-03

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add name column (temporarily nullable so we can backfill).
    op.add_column("sources", sa.Column("name", sa.Text(), nullable=True))

    # 2. Backfill: name = source_type for all existing rows.
    op.execute("UPDATE sources SET name = source_type")

    # 3. Make name NOT NULL now that all rows have a value.
    op.alter_column("sources", "name", nullable=False)

    # 4. Drop the old unique constraint.
    op.drop_constraint("sources_plugin_id_source_type_key", "sources", type_="unique")

    # 5. Add new unique constraint on (plugin_id, name).
    op.create_unique_constraint("sources_plugin_id_name_key", "sources", ["plugin_id", "name"])

    # 6. Drop old source_type CHECK constraint and add updated one.
    op.drop_constraint("sources_source_type_check", "sources", type_="check")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support',"
        "'webpage','rest_endpoint')",
    )


def downgrade() -> None:
    # Reverse order.
    op.drop_constraint("sources_source_type_check", "sources", type_="check")
    op.create_check_constraint(
        "sources_source_type_check",
        "sources",
        "source_type IN ("
        "'github_readme','github_changelog','github_docs','github_issues',"
        "'wporg_faq','wporg_changelog','wporg_support')",
    )
    op.drop_constraint("sources_plugin_id_name_key", "sources", type_="unique")
    op.create_unique_constraint(
        "sources_plugin_id_source_type_key", "sources", ["plugin_id", "source_type"]
    )
    op.drop_column("sources", "name")
```

- [ ] **Step 2: Run migration**

```bash
cd apps/api
docker compose exec app alembic upgrade head
# OR if running locally:
uv run alembic upgrade head
```

Expected: `Running upgrade 0009 -> 0010`

- [ ] **Step 3: Verify schema**

```bash
docker exec wp-support-rag-postgres-1 psql -U wprag -d wprag -c "\d sources"
```

Expected: `name` column present, `sources_plugin_id_name_key` unique constraint.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/db/migrations/versions/20260603_0010_webpage_rest_sources.py
git commit -m "feat(db): add Source.name, relax unique constraint, add webpage+rest_endpoint types"
```

---

## Task 2: Update Source Model + SOURCE_TYPES

**Files:**
- Modify: `apps/api/app/db/models.py`

- [ ] **Step 1: Expand SOURCE_TYPES and add name to Source**

In `apps/api/app/db/models.py`, make these two changes:

Change `SOURCE_TYPES` (lines ~52-60):
```python
SOURCE_TYPES = (
    "github_readme",
    "github_changelog",
    "github_docs",
    "github_issues",
    "wporg_faq",
    "wporg_changelog",
    "wporg_support",
    "webpage",
    "rest_endpoint",
)
```

Change `Source.__table_args__` and add the `name` column. Replace the entire `Source` class body from `__tablename__` to the end of `last_ingested_at`:

```python
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ("
            "'github_readme','github_changelog','github_docs',"
            "'github_issues','wporg_faq','wporg_changelog','wporg_support',"
            "'webpage','rest_endpoint')",
            name="sources_source_type_check",
        ),
        UniqueConstraint("plugin_id", "name", name="sources_plugin_id_name_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Verify import — no new imports needed** (Text, UniqueConstraint already imported)

```bash
cd apps/api && python -c "from app.db.models import Source, SOURCE_TYPES; print(SOURCE_TYPES)"
```

Expected: tuple with `webpage` and `rest_endpoint` at end.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/db/models.py
git commit -m "feat(models): add Source.name, expand SOURCE_TYPES with webpage+rest_endpoint"
```

---

## Task 3: Update Schemas + Routes (source_id params, name field, config endpoint)

**Files:**
- Modify: `apps/api/app/api/schemas.py`
- Modify: `apps/api/app/api/routes_admin.py`

### 3a — Schemas

- [ ] **Step 1: Update SourceSummary — add name**

In `schemas.py`, add `name: str` to `SourceSummary` after `source_type`:

```python
class SourceSummary(BaseModel):
    source_id: str
    source_type: str
    name: str
    enabled: bool
    last_ingested_at: str | None
    chunk_count: int = 0
    run_status: str | None = None
    run_chunks: int | None = None
    run_docs: int | None = None
    run_error: str | None = None
    run_finished_at: str | None = None
```

- [ ] **Step 2: Update AddSourceRequest — add name and config**

Replace `AddSourceRequest`:

```python
class AddSourceRequest(BaseModel):
    """Add a source to an existing plugin.

    Attributes:
        source_type: The source kind to add.
        name: Human label; required for webpage/rest_endpoint; auto-set for others.
        config: Adapter-specific configuration.
    """

    source_type: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
```

Add `from typing import Any` if not already at top (it is already imported via `Literal`).
Add `Field` to pydantic imports if not present — check line 1-5 of schemas.py; `Field` is already imported.

- [ ] **Step 3: Add PatchConfigRequest**

After `PatchSourceRequest`, add:

```python
class PatchConfigRequest(BaseModel):
    """Update the config of an existing source.

    Attributes:
        config: Full replacement config dict.
    """

    config: dict[str, Any]
```

### 3b — Routes

- [ ] **Step 4: Add _get_source_by_id helper** (add after existing `_get_source_or_404` at line ~99):

```python
async def _get_source_by_id_or_404(
    session: AsyncSession, plugin_slug: str, source_id: uuid.UUID
) -> tuple[Plugin, Source]:
    """Return (plugin, source) by source UUID or raise 404."""
    plugin = await get_plugin_by_slug(session, plugin_slug)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plugin not found")
    source = await session.get(Source, source_id)
    if source is None or source.plugin_id != plugin.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return plugin, source
```

Add `import uuid` to routes_admin.py if not present (check top — already imported via sqlalchemy? Check: `from sqlalchemy import Select, Text, cast, func, select` — uuid needs explicit import).

- [ ] **Step 5: Update list_plugin_sources to include name in SourceSummary**

In the `summaries.append(SourceSummary(...))` block (~line 571), add `name=source.name`:

```python
        summaries.append(
            SourceSummary(
                source_id=str(source.id),
                source_type=source.source_type,
                name=source.name,
                enabled=source.enabled,
                last_ingested_at=source.last_ingested_at.isoformat()
                if source.last_ingested_at
                else None,
                chunk_count=chunk_count_map.get(source.id, 0),
                run_status=run.status if run else None,
                run_chunks=run.chunks_created if run else None,
                run_docs=run.documents_processed if run else None,
                run_error=run.error if run else None,
                run_finished_at=run.finished_at.isoformat()
                if run and run.finished_at is not None
                else None,
            )
        )
```

- [ ] **Step 6: Update add_plugin_source — validate config, set name**

Replace the entire `add_plugin_source` function body (keeping decorator):

```python
async def add_plugin_source(
    plugin_slug: str,
    payload: AddSourceRequest,
    _: object = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
) -> SourceSummary:
    """Add a new source to an existing plugin (FR-PM-2)."""
    _MULTI_INSTANCE_TYPES = {"webpage", "rest_endpoint"}
    plugin = await get_plugin_by_slug(session, plugin_slug)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plugin not found")

    # Resolve name: required for multi-instance types, auto-set for single-instance.
    if payload.source_type in _MULTI_INSTANCE_TYPES:
        if not payload.name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name is required for webpage and rest_endpoint sources",
            )
        name = payload.name
    else:
        name = payload.source_type  # single-instance: name = type, enforced

    # Validate required config fields for configurable types.
    if payload.source_type == "webpage":
        if not payload.config.get("url"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="webpage source requires config.url",
            )
        depth = payload.config.get("max_depth", 2)
        if not isinstance(depth, int) or not (1 <= depth <= 5):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="webpage config.max_depth must be an integer between 1 and 5",
            )
    elif payload.source_type == "rest_endpoint":
        if not payload.config.get("url"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rest_endpoint source requires config.url",
            )
        if not payload.config.get("content_field"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rest_endpoint source requires config.content_field",
            )
        if not payload.config.get("id_field"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="rest_endpoint source requires config.id_field",
            )

    source = Source(
        plugin_id=plugin.id,
        source_type=payload.source_type,
        name=name,
        config=payload.config,
    )
    session.add(source)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a source with this name already exists for this plugin",
        )
    return SourceSummary(
        source_id=str(source.id),
        source_type=source.source_type,
        name=source.name,
        enabled=source.enabled,
        last_ingested_at=None,
    )
```

- [ ] **Step 7: Replace patch_plugin_source to use source_id**

Replace the route decorator + function:

```python
@router.patch(
    "/plugins/{plugin_slug}/sources/{source_id}",
    response_model=SourceSummary,
)
async def patch_plugin_source(
    plugin_slug: str,
    source_id: uuid.UUID,
    payload: PatchSourceRequest,
    _: object = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
) -> SourceSummary:
    """Enable or disable a plugin source (FR-PM-3)."""
    _, source = await _get_source_by_id_or_404(session, plugin_slug, source_id)
    source.enabled = payload.enabled
    await session.commit()
    return SourceSummary(
        source_id=str(source.id),
        source_type=source.source_type,
        name=source.name,
        enabled=source.enabled,
        last_ingested_at=source.last_ingested_at.isoformat()
        if source.last_ingested_at
        else None,
    )
```

- [ ] **Step 8: Replace delete_plugin_source to use source_id**

```python
@router.delete(
    "/plugins/{plugin_slug}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plugin_source(
    plugin_slug: str,
    source_id: uuid.UUID,
    _: object = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Remove a source from a plugin (FR-PM-2)."""
    _, source = await _get_source_by_id_or_404(session, plugin_slug, source_id)
    await session.delete(source)
    await session.commit()
```

- [ ] **Step 9: Add patch config route** (insert after delete_plugin_source):

```python
@router.patch(
    "/plugins/{plugin_slug}/sources/{source_id}/config",
    response_model=SourceSummary,
)
async def patch_plugin_source_config(
    plugin_slug: str,
    source_id: uuid.UUID,
    payload: PatchConfigRequest,
    _: object = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
) -> SourceSummary:
    """Replace a source's adapter config."""
    _, source = await _get_source_by_id_or_404(session, plugin_slug, source_id)
    source.config = payload.config
    await session.commit()
    return SourceSummary(
        source_id=str(source.id),
        source_type=source.source_type,
        name=source.name,
        enabled=source.enabled,
        last_ingested_at=source.last_ingested_at.isoformat()
        if source.last_ingested_at
        else None,
    )
```

Also add `PatchConfigRequest` to the schema imports at the top of `routes_admin.py`.

- [ ] **Step 10: Replace trigger_ingest_source to use source_id**

```python
@router.post("/ingest/{plugin_slug}/sources/{source_id}", response_model=IngestTriggerResponse)
async def trigger_ingest_source(
    plugin_slug: str,
    source_id: uuid.UUID,
    _: object = Depends(require_permission("ingestion:trigger")),
    session: AsyncSession = Depends(get_session),
) -> IngestTriggerResponse:
    """Dispatch ingestion for a single source (FR-IN-6)."""
    from app.ingestion.tasks import ingest_source_task

    _, source = await _get_source_by_id_or_404(session, plugin_slug, source_id)
    run = IngestionRun(source_id=source.id, status="queued")
    session.add(run)
    await session.flush()
    ingest_source_task.delay(str(source.id), str(run.id))
    await session.commit()
    return IngestTriggerResponse(plugin_slug=plugin_slug, enqueued_sources=1)
```

- [ ] **Step 11: Add uuid import to routes_admin.py** (top of file):

```python
import uuid
```

- [ ] **Step 12: Smoke test**

```bash
cd apps/api && python -c "from app.api.routes_admin import router; print('OK')"
```

- [ ] **Step 13: Commit**

```bash
git add apps/api/app/api/schemas.py apps/api/app/api/routes_admin.py
git commit -m "feat(api): source_id params, name field, config-patch route, webpage+rest validation"
```

---

## Task 4: WebpageAdapter

**Files:**
- Create: `apps/api/app/ingestion/adapters/webpage.py`

- [ ] **Step 1: Add dependencies**

In `apps/api/pyproject.toml`, add to `dependencies`:
```toml
"beautifulsoup4>=4.12",
"lxml>=5.0",
```

Install in the running container:
```bash
docker compose exec app pip install beautifulsoup4 lxml
docker compose exec worker pip install beautifulsoup4 lxml
```

(The Dockerfile will pick them up on next build.)

- [ ] **Step 2: Write the adapter**

Create `apps/api/app/ingestion/adapters/webpage.py`:

```python
"""Webpage crawler source adapter.

Fetches a start URL and follows internal links up to a configurable depth,
yielding one RawDocument per page. Content is extracted from a CSS selector
and normalised as HTML by the shared normaliser.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.ingestion.adapters._http import build_client
from app.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_DEFAULT_SELECTOR = "main, article, [role=main], body"


class WebpageAdapter:
    """Adapter that crawls a website up to a configurable depth (FR-IN-x)."""

    handles: ClassVar[tuple[str, ...]] = ("webpage",)

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """BFS-crawl from config.url up to config.max_depth.

        Args:
            ctx: Source context; ``config.url`` must be set.

        Yields:
            RawDocument: One per successfully fetched page.

        Raises:
            SourceFetchError: If config.url is missing.
        """
        config = ctx.config
        start_url: str = config.get("url", "")
        if not start_url:
            raise SourceFetchError("webpage source requires config.url")

        max_depth: int = int(config.get("max_depth", 2))
        selector: str = config.get("selector", _DEFAULT_SELECTOR)
        url_filter_pattern: str | None = config.get("url_filter")

        parsed_start = urlparse(start_url)
        default_filter = rf"^{re.escape(parsed_start.scheme)}://{re.escape(parsed_start.netloc)}(/|$)"
        url_filter = re.compile(url_filter_pattern or default_filter)

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])

        async with build_client(self._settings) as client:
            while queue:
                url, depth = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)

                try:
                    response = await client.get(url)
                except Exception:
                    continue  # non-fatal: skip unreachable pages

                if response.status_code != 200:
                    continue

                html = response.text
                soup = BeautifulSoup(html, "lxml")

                # Extract content from the configured selector.
                content_el = soup.select_one(selector)
                content = content_el.get_text(separator="\n", strip=True) if content_el else ""
                if not content.strip():
                    content = soup.get_text(separator="\n", strip=True)

                title_el = soup.find("title")
                title = title_el.get_text(strip=True) if title_el else url

                yield RawDocument(
                    external_id=url,
                    title=title,
                    doc_type="webpage",
                    content=html,
                    content_type="html",
                    source_url=url,
                    metadata={"depth": depth, "plugin_slug": ctx.plugin_slug},
                )

                # Follow links if we haven't hit max_depth.
                if depth < max_depth:
                    for tag in soup.find_all("a", href=True):
                        href: str = tag["href"]
                        abs_url = urljoin(url, href).split("#")[0]
                        if abs_url not in visited and url_filter.match(abs_url):
                            queue.append((abs_url, depth + 1))

                await asyncio.sleep(self._settings.ingest_polite_delay_seconds)
```

- [ ] **Step 3: Write unit test**

Create `apps/api/tests/test_webpage_adapter.py`:

```python
"""Unit tests for WebpageAdapter."""

from __future__ import annotations

import pytest
import respx
import httpx

from app.config import get_settings
from app.ingestion.adapters.base import SourceContext, SourceFetchError
from app.ingestion.adapters.webpage import WebpageAdapter


def _ctx(config: dict) -> SourceContext:
    return SourceContext(plugin_slug="test-plugin", source_type="webpage", config=config)


@pytest.mark.asyncio
async def test_webpage_adapter_no_url_raises():
    adapter = WebpageAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="config.url"):
        async for _ in adapter.fetch(_ctx({})):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_fetches_start_url():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text="<html><head><title>Hello</title></head><body><main>Content here</main></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    adapter = WebpageAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({"url": "http://example.com/", "max_depth": 0}))]
    assert len(docs) == 1
    assert docs[0].external_id == "http://example.com/"
    assert docs[0].title == "Hello"
    assert docs[0].content_type == "html"
    assert docs[0].doc_type == "webpage"


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_follows_links():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><main>Root</main><a href="/page2">p2</a></body></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("http://example.com/page2").mock(
        return_value=httpx.Response(
            200,
            text="<html><body><main>Page 2</main></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    adapter = WebpageAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({"url": "http://example.com/", "max_depth": 1}))]
    urls = {d.external_id for d in docs}
    assert "http://example.com/" in urls
    assert "http://example.com/page2" in urls


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_respects_url_filter():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><a href="/docs/page">docs</a><a href="http://other.com/">ext</a></body></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("http://example.com/docs/page").mock(
        return_value=httpx.Response(200, text="<html><body>docs</body></html>",
                                     headers={"content-type": "text/html"})
    )
    adapter = WebpageAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({"url": "http://example.com/", "max_depth": 1,
                  "url_filter": r"^http://example\.com/docs/"})
        )
    ]
    urls = {d.external_id for d in docs}
    assert "http://example.com/docs/page" in urls
    assert "http://other.com/" not in urls
```

- [ ] **Step 4: Install respx for mocking and run tests**

```bash
cd apps/api
pip install respx
pytest tests/test_webpage_adapter.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/ingestion/adapters/webpage.py apps/api/pyproject.toml apps/api/tests/test_webpage_adapter.py
git commit -m "feat(adapters): add WebpageAdapter with BFS crawl and depth/filter config"
```

---

## Task 5: RestEndpointAdapter

**Files:**
- Create: `apps/api/app/ingestion/adapters/rest_endpoint.py`

- [ ] **Step 1: Write the adapter**

Create `apps/api/app/ingestion/adapters/rest_endpoint.py`:

```python
"""REST endpoint source adapter.

Fetches a paginated JSON API and maps each item to a RawDocument using
configured field paths. Supports four pagination strategies: none, page_param,
link_header, and cursor.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.config import Settings, get_settings
from app.ingestion.adapters._http import build_client
from app.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _get_nested(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path in a nested dict, e.g. 'data.results'."""
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


class RestEndpointAdapter:
    """Adapter for paginated JSON REST APIs."""

    handles: ClassVar[tuple[str, ...]] = ("rest_endpoint",)

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Fetch all pages from the REST endpoint and yield one RawDocument per item.

        Args:
            ctx: Source context; ``config.url``, ``config.content_field``,
                and ``config.id_field`` must be set.

        Yields:
            RawDocument: One per item in the API response.

        Raises:
            SourceFetchError: If required config is missing or the API is unreachable.
        """
        cfg = ctx.config
        base_url: str = cfg.get("url", "")
        if not base_url:
            raise SourceFetchError("rest_endpoint source requires config.url")
        content_field: str = cfg.get("content_field", "")
        if not content_field:
            raise SourceFetchError("rest_endpoint source requires config.content_field")
        id_field: str = cfg.get("id_field", "")
        if not id_field:
            raise SourceFetchError("rest_endpoint source requires config.id_field")

        method: str = cfg.get("method", "GET").upper()
        extra_headers: dict[str, str] = cfg.get("headers", {})
        query_params: dict[str, str] = dict(cfg.get("query_params", {}))
        pagination: str = cfg.get("pagination", "none")
        page_param: str = cfg.get("page_param", "page")
        page_size_param: str = cfg.get("page_size_param", "per_page")
        page_size: int = int(cfg.get("page_size", 100))
        cursor_field: str = cfg.get("cursor_field", "")
        items_path: str = cfg.get("items_path", "")
        title_field: str = cfg.get("title_field", "")
        url_field: str = cfg.get("url_field", "")

        async with build_client(self._settings, headers=extra_headers) as client:
            if pagination == "page_param":
                async for doc in self._fetch_page_param(
                    client, base_url, method, query_params,
                    page_param, page_size_param, page_size, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc

            elif pagination == "link_header":
                async for doc in self._fetch_link_header(
                    client, base_url, method, query_params, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc

            elif pagination == "cursor":
                async for doc in self._fetch_cursor(
                    client, base_url, method, query_params, cursor_field, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc

            else:  # "none"
                async for doc in self._fetch_single(
                    client, base_url, method, query_params, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc

    def _item_to_doc(
        self,
        item: dict[str, Any],
        id_field: str,
        content_field: str,
        title_field: str,
        url_field: str,
        ctx: SourceContext,
    ) -> RawDocument | None:
        """Map one API item dict to a RawDocument, or None if required fields missing."""
        external_id = str(item.get(id_field, ""))
        content = str(item.get(content_field, ""))
        if not external_id or not content:
            return None
        title = str(item.get(title_field, "")) if title_field else None
        source_url = str(item.get(url_field, "")) if url_field else ctx.config.get("url", "")
        return RawDocument(
            external_id=external_id,
            title=title or None,
            doc_type="rest_endpoint",
            content=content,
            content_type="text",
            source_url=source_url,
            metadata={"plugin_slug": ctx.plugin_slug},
        )

    async def _request_json(
        self, client: Any, method: str, url: str, params: dict
    ) -> tuple[Any, dict]:
        """Make a request and return (parsed_json, response_headers)."""
        resp = await client.request(method, url, params=params)
        if resp.status_code != 200:
            raise SourceFetchError(
                f"rest_endpoint returned HTTP {resp.status_code} for {url}"
            )
        return resp.json(), dict(resp.headers)

    async def _fetch_single(
        self, client: Any, url: str, method: str, params: dict,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        data, _ = await self._request_json(client, method, url, params)
        items = _get_nested(data, items_path) if items_path else data
        if not isinstance(items, list):
            items = [items] if isinstance(items, dict) else []
        for item in items:
            doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
            if doc:
                yield doc

    async def _fetch_page_param(
        self, client: Any, url: str, method: str, params: dict,
        page_param: str, page_size_param: str, page_size: int,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        page = 1
        while True:
            p = {**params, page_param: page, page_size_param: page_size}
            data, _ = await self._request_json(client, method, url, p)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list) or not items:
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            if len(items) < page_size:
                break
            page += 1

    async def _fetch_link_header(
        self, client: Any, url: str, method: str, params: dict,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        next_url: str | None = url
        while next_url:
            data, headers = await self._request_json(client, method, next_url, params)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list):
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            link_header = headers.get("link", "")
            match = _LINK_RE.search(link_header)
            next_url = match.group(1) if match else None
            params = {}  # next_url already has params baked in

    async def _fetch_cursor(
        self, client: Any, url: str, method: str, params: dict,
        cursor_field: str, items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        cursor: str | None = None
        while True:
            p = {**params, **({"cursor": cursor} if cursor else {})}
            data, _ = await self._request_json(client, method, url, p)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list) or not items:
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            cursor = _get_nested(data, cursor_field) if cursor_field else None
            if not cursor:
                break
```

- [ ] **Step 2: Write unit test**

Create `apps/api/tests/test_rest_endpoint_adapter.py`:

```python
"""Unit tests for RestEndpointAdapter."""

from __future__ import annotations

import pytest
import respx
import httpx

from app.config import get_settings
from app.ingestion.adapters.base import SourceContext, SourceFetchError
from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter


def _ctx(config: dict) -> SourceContext:
    return SourceContext(plugin_slug="test-plugin", source_type="rest_endpoint", config=config)


BASE_CFG = {
    "url": "http://api.example.com/items",
    "id_field": "id",
    "content_field": "body",
}


@pytest.mark.asyncio
async def test_missing_url_raises():
    adapter = RestEndpointAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="config.url"):
        async for _ in adapter.fetch(_ctx({"id_field": "id", "content_field": "body"})):
            pass


@pytest.mark.asyncio
async def test_missing_content_field_raises():
    adapter = RestEndpointAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="content_field"):
        async for _ in adapter.fetch(_ctx({"url": "http://x.com", "id_field": "id"})):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_fetch_single_page():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json=[
            {"id": "1", "body": "Hello world", "title": "Post 1"},
            {"id": "2", "body": "Second post"},
        ])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({**BASE_CFG, "title_field": "title"}))]
    assert len(docs) == 2
    assert docs[0].external_id == "1"
    assert docs[0].content == "Hello world"
    assert docs[0].title == "Post 1"
    assert docs[1].title is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_paginated_page_param():
    respx.get("http://api.example.com/items", params={"page": "1", "per_page": "2"}).mock(
        return_value=httpx.Response(200, json=[{"id": "1", "body": "a"}, {"id": "2", "body": "b"}])
    )
    respx.get("http://api.example.com/items", params={"page": "2", "per_page": "2"}).mock(
        return_value=httpx.Response(200, json=[{"id": "3", "body": "c"}])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({**BASE_CFG, "pagination": "page_param", "page_size": 2})
        )
    ]
    assert [d.external_id for d in docs] == ["1", "2", "3"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_items_path():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json={"data": {"results": [{"id": "1", "body": "x"}]}})
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({**BASE_CFG, "items_path": "data.results"}))]
    assert len(docs) == 1
    assert docs[0].external_id == "1"


@pytest.mark.asyncio
@respx.mock
async def test_bearer_auth_header():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "body": "secret"}])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({**BASE_CFG, "headers": {"Authorization": "Bearer tok123"}})
        )
    ]
    assert len(docs) == 1
    sent_req = respx.calls[0].request
    assert sent_req.headers["authorization"] == "Bearer tok123"
```

- [ ] **Step 3: Run tests**

```bash
cd apps/api && pytest tests/test_rest_endpoint_adapter.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/ingestion/adapters/rest_endpoint.py apps/api/tests/test_rest_endpoint_adapter.py
git commit -m "feat(adapters): add RestEndpointAdapter with pagination strategies and field mapping"
```

---

## Task 6: Register New Adapters in Tasks

**Files:**
- Modify: `apps/api/app/ingestion/tasks.py`

- [ ] **Step 1: Import and register adapters**

In `apps/api/app/ingestion/tasks.py`, add imports after the existing adapter imports:

```python
from app.ingestion.adapters.webpage import WebpageAdapter
from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter
```

Replace the `_ADAPTERS` dict:

```python
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
```

- [ ] **Step 2: Verify**

```bash
cd apps/api && python -c "
from app.ingestion.tasks import resolve_adapter
print(resolve_adapter('webpage'))
print(resolve_adapter('rest_endpoint'))
print('OK')
"
```

Expected: prints two adapter objects then `OK`.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/ingestion/tasks.py
git commit -m "feat(tasks): register WebpageAdapter and RestEndpointAdapter"
```

---

## Task 7: Frontend — Types, API Client

**Files:**
- Modify: `apps/admin/src/types/api.ts`
- Modify: `apps/admin/src/api/admin.ts`

- [ ] **Step 1: Update SOURCE_TYPES and SourceSummary**

In `apps/admin/src/types/api.ts`:

Replace `SOURCE_TYPES`:
```typescript
export const SOURCE_TYPES = [
  "github_readme",
  "github_changelog",
  "github_docs",
  "github_issues",
  "wporg_faq",
  "wporg_changelog",
  "wporg_support",
  "webpage",
  "rest_endpoint",
] as const;
```

Add `name: string` to `SourceSummary`:
```typescript
export interface SourceSummary {
  source_id: string;
  source_type: string;
  name: string;
  enabled: boolean;
  last_ingested_at: string | null;
  chunk_count: number;
  run_status: string | null;
  run_chunks: number | null;
  run_docs: number | null;
  run_error: string | null;
  run_finished_at: string | null;
}
```

- [ ] **Step 2: Update admin.ts API functions**

In `apps/admin/src/api/admin.ts`:

Replace `addSource`:
```typescript
export async function addSource(
  slug: string,
  sourceType: string,
  name: string,
  config: Record<string, unknown> = {},
): Promise<SourceSummary> {
  const res = await apiClient.post<SourceSummary>(`/api/v1/admin/plugins/${slug}/sources`, {
    source_type: sourceType,
    name,
    config,
  });
  return res.data;
}
```

Replace `patchSource`:
```typescript
export async function patchSource(
  slug: string,
  sourceId: string,
  payload: PatchSourcePayload,
): Promise<SourceSummary> {
  const res = await apiClient.patch<SourceSummary>(
    `/api/v1/admin/plugins/${slug}/sources/${sourceId}`,
    payload,
  );
  return res.data;
}
```

Replace `deleteSource`:
```typescript
export async function deleteSource(slug: string, sourceId: string): Promise<void> {
  await apiClient.delete(`/api/v1/admin/plugins/${slug}/sources/${sourceId}`);
}
```

Replace `ingestSource`:
```typescript
export async function ingestSource(slug: string, sourceId: string): Promise<IngestTriggerResponse> {
  const res = await apiClient.post<IngestTriggerResponse>(
    `/api/v1/admin/ingest/${slug}/sources/${sourceId}`,
  );
  return res.data;
}
```

Add `patchSourceConfig` after `ingestSource`:
```typescript
export async function patchSourceConfig(
  slug: string,
  sourceId: string,
  config: Record<string, unknown>,
): Promise<SourceSummary> {
  const res = await apiClient.patch<SourceSummary>(
    `/api/v1/admin/plugins/${slug}/sources/${sourceId}/config`,
    { config },
  );
  return res.data;
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/admin/src/types/api.ts apps/admin/src/api/admin.ts
git commit -m "feat(frontend): update source types, add name field, switch to source_id params"
```

---

## Task 8: Frontend — AddSourceModal

**Files:**
- Create: `apps/admin/src/features/AddSourceModal.tsx`

- [ ] **Step 1: Create the two-step modal**

Create `apps/admin/src/features/AddSourceModal.tsx`:

```tsx
// Two-step add-source modal: type picker → config form. Author: Al Amin Ahamed.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addSource } from "@/api/admin";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ToastProvider";
import { extractErrorMessage } from "@/lib/queryClient";
import { SOURCE_TYPES } from "@/types/api";

const MULTI_INSTANCE_TYPES = new Set(["webpage", "rest_endpoint"]);

const TYPE_ICONS: Record<string, string> = {
  github_readme: "ti-brand-github",
  github_changelog: "ti-file-text",
  github_docs: "ti-book",
  github_issues: "ti-message-circle",
  wporg_faq: "ti-help-circle",
  wporg_changelog: "ti-clock",
  wporg_support: "ti-messages",
  webpage: "ti-world",
  rest_endpoint: "ti-api",
};

interface WebpageConfig {
  url: string;
  name: string;
  max_depth: number;
  selector: string;
  url_filter: string;
}

interface RestConfig {
  url: string;
  name: string;
  method: "GET" | "POST";
  auth_type: "none" | "bearer" | "api_key" | "custom";
  bearer_token: string;
  api_key_header: string;
  api_key_value: string;
  content_field: string;
  title_field: string;
  url_field: string;
  id_field: string;
  pagination: "none" | "page_param" | "link_header" | "cursor";
  page_param: string;
  page_size_param: string;
  page_size: number;
  cursor_field: string;
  items_path: string;
}

function buildHeaders(cfg: RestConfig): Record<string, string> {
  if (cfg.auth_type === "bearer") return { Authorization: `Bearer ${cfg.bearer_token}` };
  if (cfg.auth_type === "api_key") return { [cfg.api_key_header]: cfg.api_key_value };
  return {};
}

function buildRestConfig(cfg: RestConfig): Record<string, unknown> {
  const out: Record<string, unknown> = {
    url: cfg.url,
    method: cfg.method,
    content_field: cfg.content_field,
    id_field: cfg.id_field,
    pagination: cfg.pagination,
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

function WebpageConfigForm({
  cfg,
  setCfg,
}: {
  cfg: WebpageConfig;
  setCfg: (c: WebpageConfig) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="e.g. Plugin Docs Site"
          value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Start URL <span className="text-destructive">*</span></label>
        <input
          type="url"
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="https://docs.example.com/"
          value={cfg.url}
          onChange={(e) => {
            const url = e.target.value;
            const hostname = (() => { try { return new URL(url).hostname; } catch { return ""; } })();
            setCfg({ ...cfg, url, name: cfg.name || hostname });
          }}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Max depth (1–5)</label>
        <div className="flex items-center gap-3">
          <input
            type="range" min={1} max={5} value={cfg.max_depth}
            onChange={(e) => setCfg({ ...cfg, max_depth: Number(e.target.value) })}
            className="flex-1"
          />
          <span className="text-sm font-mono w-4">{cfg.max_depth}</span>
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">CSS selector <span className="text-muted-foreground">(optional)</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="main, article, [role=main], body"
          value={cfg.selector}
          onChange={(e) => setCfg({ ...cfg, selector: e.target.value })}
        />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">URL filter regex <span className="text-muted-foreground">(optional — defaults to same domain)</span></label>
        <input
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="^https://docs\.example\.com/"
          value={cfg.url_filter}
          onChange={(e) => setCfg({ ...cfg, url_filter: e.target.value })}
        />
      </div>
    </div>
  );
}

function RestConfigForm({ cfg, setCfg }: { cfg: RestConfig; setCfg: (c: RestConfig) => void }) {
  return (
    <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
      <div>
        <label className="block text-xs font-medium mb-1">Name <span className="text-destructive">*</span></label>
        <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="e.g. Plugin REST API" value={cfg.name}
          onChange={(e) => setCfg({ ...cfg, name: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Endpoint URL <span className="text-destructive">*</span></label>
        <input type="url" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="https://api.example.com/v1/posts" value={cfg.url}
          onChange={(e) => setCfg({ ...cfg, url: e.target.value })} />
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="block text-xs font-medium mb-1">Method</label>
          <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
            value={cfg.method} onChange={(e) => setCfg({ ...cfg, method: e.target.value as "GET" | "POST" })}>
            <option value="GET">GET</option>
            <option value="POST">POST</option>
          </select>
        </div>
        <div className="flex-1">
          <label className="block text-xs font-medium mb-1">Auth</label>
          <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
            value={cfg.auth_type} onChange={(e) => setCfg({ ...cfg, auth_type: e.target.value as RestConfig["auth_type"] })}>
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="api_key">API key header</option>
          </select>
        </div>
      </div>
      {cfg.auth_type === "bearer" && (
        <div>
          <label className="block text-xs font-medium mb-1">Bearer token</label>
          <input type="password" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={cfg.bearer_token} onChange={(e) => setCfg({ ...cfg, bearer_token: e.target.value })} />
        </div>
      )}
      {cfg.auth_type === "api_key" && (
        <div className="flex gap-2">
          <input className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
            placeholder="Header name (e.g. X-API-Key)" value={cfg.api_key_header}
            onChange={(e) => setCfg({ ...cfg, api_key_header: e.target.value })} />
          <input type="password" className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
            placeholder="Value" value={cfg.api_key_value}
            onChange={(e) => setCfg({ ...cfg, api_key_value: e.target.value })} />
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium mb-1">Content field <span className="text-destructive">*</span></label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="body" value={cfg.content_field}
            onChange={(e) => setCfg({ ...cfg, content_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">ID field <span className="text-destructive">*</span></label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="id" value={cfg.id_field}
            onChange={(e) => setCfg({ ...cfg, id_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Title field</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="title" value={cfg.title_field}
            onChange={(e) => setCfg({ ...cfg, title_field: e.target.value })} />
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">URL field</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="url" value={cfg.url_field}
            onChange={(e) => setCfg({ ...cfg, url_field: e.target.value })} />
        </div>
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Items path <span className="text-muted-foreground">(dot-separated, e.g. data.results)</span></label>
        <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
          placeholder="data" value={cfg.items_path}
          onChange={(e) => setCfg({ ...cfg, items_path: e.target.value })} />
      </div>
      <div>
        <label className="block text-xs font-medium mb-1">Pagination</label>
        <select className="w-full rounded border border-border bg-background px-2 py-1.5 text-sm focus:outline-none"
          value={cfg.pagination} onChange={(e) => setCfg({ ...cfg, pagination: e.target.value as RestConfig["pagination"] })}>
          <option value="none">None (single request)</option>
          <option value="page_param">Page number param</option>
          <option value="link_header">Link header (RFC 5988)</option>
          <option value="cursor">Cursor field</option>
        </select>
      </div>
      {cfg.pagination === "page_param" && (
        <div className="grid grid-cols-3 gap-2">
          <div>
            <label className="block text-xs font-medium mb-1">Page param</label>
            <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
              value={cfg.page_param} onChange={(e) => setCfg({ ...cfg, page_param: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Size param</label>
            <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
              value={cfg.page_size_param} onChange={(e) => setCfg({ ...cfg, page_size_param: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Page size</label>
            <input type="number" className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none"
              value={cfg.page_size} onChange={(e) => setCfg({ ...cfg, page_size: Number(e.target.value) })} />
          </div>
        </div>
      )}
      {cfg.pagination === "cursor" && (
        <div>
          <label className="block text-xs font-medium mb-1">Cursor field (dot-path in response)</label>
          <input className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none"
            placeholder="next_cursor" value={cfg.cursor_field}
            onChange={(e) => setCfg({ ...cfg, cursor_field: e.target.value })} />
        </div>
      )}
    </div>
  );
}

const DEFAULT_WEBPAGE: WebpageConfig = { url: "", name: "", max_depth: 2, selector: "", url_filter: "" };
const DEFAULT_REST: RestConfig = {
  url: "", name: "", method: "GET", auth_type: "none",
  bearer_token: "", api_key_header: "", api_key_value: "",
  content_field: "", title_field: "", url_field: "", id_field: "",
  pagination: "none", page_param: "page", page_size_param: "per_page",
  page_size: 100, cursor_field: "", items_path: "",
};

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

  const singleTypes = SOURCE_TYPES.filter((t) => !MULTI_INSTANCE_TYPES.has(t) && !usedTypes.has(t));
  const multiTypes = SOURCE_TYPES.filter((t) => MULTI_INSTANCE_TYPES.has(t));

  function handlePickType(type: string) {
    if (MULTI_INSTANCE_TYPES.has(type)) {
      setSelectedType(type);
      setStep("configure");
    } else {
      mutation.mutate({ type, name: type, config: {} });
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
    } else {
      mutation.mutate({
        type: "rest_endpoint",
        name: restCfg.name,
        config: buildRestConfig(restCfg),
      });
    }
  }

  const configValid = selectedType === "webpage"
    ? webCfg.url.trim() !== "" && webCfg.name.trim() !== ""
    : restCfg.url.trim() !== "" && restCfg.name.trim() !== "" &&
      restCfg.content_field.trim() !== "" && restCfg.id_field.trim() !== "";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-background border border-border rounded-xl shadow-xl w-full max-w-lg mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-base font-semibold">
            {step === "pick" ? "Add source" : `Configure ${selectedType.replace("_", " ")}`}
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <i className="ti ti-x text-sm" />
          </button>
        </div>

        <div className="p-5">
          {step === "pick" ? (
            <div className="space-y-4">
              {singleTypes.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">GitHub &amp; WordPress.org</p>
                  <div className="grid grid-cols-2 gap-2">
                    {singleTypes.map((t) => (
                      <button
                        key={t}
                        onClick={() => handlePickType(t)}
                        disabled={mutation.isPending}
                        className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors disabled:opacity-50"
                      >
                        <i className={`ti ${TYPE_ICONS[t] ?? "ti-file"} text-muted-foreground`} />
                        <span className="font-mono text-[12px]">{t}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">Custom sources (multiple allowed)</p>
                <div className="grid grid-cols-2 gap-2">
                  {multiTypes.map((t) => (
                    <button
                      key={t}
                      onClick={() => handlePickType(t)}
                      className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm hover:bg-muted transition-colors"
                    >
                      <i className={`ti ${TYPE_ICONS[t] ?? "ti-file"} text-muted-foreground`} />
                      <span className="font-mono text-[12px]">{t}</span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {selectedType === "webpage" ? (
                <WebpageConfigForm cfg={webCfg} setCfg={setWebCfg} />
              ) : (
                <RestConfigForm cfg={restCfg} setCfg={setRestCfg} />
              )}
              <div className="flex justify-between pt-1">
                <Button variant="ghost" size="sm" onClick={() => setStep("pick")}>
                  ← Back
                </Button>
                <Button
                  size="sm"
                  onClick={handleSubmitConfig}
                  disabled={!configValid || mutation.isPending}
                >
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

- [ ] **Step 2: Commit**

```bash
git add apps/admin/src/features/AddSourceModal.tsx
git commit -m "feat(ui): AddSourceModal with two-step flow, WebpageConfigForm, RestConfigForm"
```

---

## Task 9: Update SourcesRow.tsx

**Files:**
- Modify: `apps/admin/src/features/SourcesRow.tsx`

- [ ] **Step 1: Rewrite SourcesRow.tsx to use source_id, show name, add edit button, use modal**

Replace the entire file content:

```tsx
// Expandable per-plugin sources table: enable/disable, per-source ingest, delete, add. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { deleteSource, ingestSource, listSources, patchSource, patchSourceConfig } from "@/api/admin";
import { useToast } from "@/components/ToastProvider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/feedback";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { relativeTime } from "@/lib/format";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { SourceSummary } from "@/types/api";
import { AddSourceModal } from "./AddSourceModal";

const RUN_STYLE: Record<string, { cls: string; icon: string; label: string }> = {
  queued:    { cls: "bg-warning/10 text-warning border-warning/20",             icon: "ti-clock",        label: "queued"    },
  running:   { cls: "bg-primary/10 text-primary border-primary/20",             icon: "ti-loader-2",     label: "running"   },
  succeeded: { cls: "bg-success/10 text-success border-success/20",             icon: "ti-circle-check", label: "succeeded" },
  failed:    { cls: "bg-destructive/10 text-destructive border-destructive/20", icon: "ti-alert-circle", label: "failed"    },
};

function RunStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  const cfg = RUN_STYLE[status] ?? { cls: "bg-muted text-muted-foreground border-border", icon: "ti-point", label: status };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", cfg.cls)}>
      <i className={cn(`ti ${cfg.icon} text-[10px]`, status === "running" && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

function EnableToggle({ enabled, loading, onToggle }: { enabled: boolean; loading: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} disabled={loading}
      aria-label={enabled ? "Disable source" : "Enable source"}
      className={cn("relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        enabled ? "bg-success" : "bg-muted-foreground/40")}>
      <span className={cn("pointer-events-none block h-3 w-3 rounded-full bg-white shadow-sm transition-transform", enabled ? "translate-x-3" : "translate-x-0")} />
    </button>
  );
}

const ACTIVE_STATUSES = new Set(["queued", "running"]);
const CONFIGURABLE_TYPES = new Set(["webpage", "rest_endpoint"]);

function SourceTableRow({
  s, slug, onToggle, onIngest, onDelete, toggleLoading, ingestLoading, deleteLoading,
}: {
  s: SourceSummary; slug: string;
  onToggle: (sourceId: string, enabled: boolean) => void;
  onIngest: (sourceId: string) => void;
  onDelete: (sourceId: string) => void;
  toggleLoading: boolean; ingestLoading: boolean; deleteLoading: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editingConfig, setEditingConfig] = useState(false);

  return (
    <tr className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors">
      {/* Name + type badge */}
      <td className="py-2.5 pl-4 pr-3">
        <div className="flex flex-col gap-0.5">
          <span className="text-[12px] font-medium text-foreground">{s.name}</span>
          {s.name !== s.source_type && (
            <span className="font-mono text-[10px] text-muted-foreground">{s.source_type}</span>
          )}
        </div>
      </td>
      <td className="pr-3">
        <EnableToggle enabled={s.enabled} loading={toggleLoading}
          onToggle={() => onToggle(s.source_id, !s.enabled)} />
      </td>
      <td className="pr-3">
        <div className="flex flex-col gap-0.5">
          <RunStatusBadge status={s.run_status} />
          {s.run_error && (
            <p className="max-w-[200px] truncate text-[10px] text-destructive" title={s.run_error}>
              {s.run_error}
            </p>
          )}
        </div>
      </td>
      <td className="pr-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {s.last_ingested_at ? relativeTime(s.last_ingested_at) : "never"}
      </td>
      <td className="pr-3 text-[12px] text-muted-foreground">
        <Badge variant={s.chunk_count > 0 ? "accent" : "secondary"} className="text-[10px]">
          {s.chunk_count.toLocaleString()}
        </Badge>
      </td>
      <td className="pr-3 text-[12px] text-muted-foreground whitespace-nowrap">
        {s.run_chunks !== null || s.run_docs !== null ? (
          <span>
            {s.run_chunks !== null ? s.run_chunks.toLocaleString() : "—"} chunks
            {" / "}
            {s.run_docs !== null ? s.run_docs.toLocaleString() : "—"} docs
          </span>
        ) : <span>—</span>}
      </td>
      <td className="pr-3 text-right">
        {confirmDelete ? (
          <span className="inline-flex items-center gap-1.5 text-[11px]">
            <span className="text-destructive font-medium">Delete?</span>
            <button type="button" onClick={() => { onDelete(s.source_id); setConfirmDelete(false); }}
              disabled={deleteLoading} className="text-destructive font-semibold hover:underline disabled:opacity-50">Yes</button>
            <button type="button" onClick={() => setConfirmDelete(false)} className="text-muted-foreground hover:underline">No</button>
          </span>
        ) : (
          <span className="inline-flex items-center gap-0.5">
            {CONFIGURABLE_TYPES.has(s.source_type) && (
              <Button variant="ghost" size="sm" onClick={() => setEditingConfig(true)}
                title="Edit config" className="h-7 w-7 p-0 text-muted-foreground">
                <i className="ti ti-settings text-[12px]" />
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => onIngest(s.source_id)}
              disabled={ingestLoading} title="Trigger ingest" className="h-7 w-7 p-0">
              <i className="ti ti-player-play text-[12px]" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}
              title="Delete this source" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive">
              <i className="ti ti-trash text-[12px]" />
            </Button>
          </span>
        )}
      </td>
    </tr>
  );
}

export function SourcesRow({ slug, colSpan }: { slug: string; colSpan: number }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [showAddModal, setShowAddModal] = useState(false);

  const sources = useQuery({
    queryKey: ["sources", slug],
    queryFn: () => listSources(slug),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return data.some((s) => s.run_status && ACTIVE_STATUSES.has(s.run_status)) ? 3000 : false;
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ sourceId, enabled }: { sourceId: string; enabled: boolean }) =>
      patchSource(slug, sourceId, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources", slug] }),
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const ingestMutation = useMutation({
    mutationFn: (sourceId: string) => ingestSource(slug, sourceId),
    onSuccess: (data) => toast.ok(`Enqueued ${data.enqueued_sources} source for ${data.plugin_slug}`),
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => deleteSource(slug, sourceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sources", slug] });
      qc.invalidateQueries({ queryKey: ["plugins"] });
      toast.ok("Source deleted");
    },
    onError: (err) => toast.err(extractErrorMessage(err)),
  });

  const usedTypes = new Set(sources.data?.map((s) => s.source_type) ?? []);

  return (
    <>
      <TableRow>
        <TableCell colSpan={colSpan} className="bg-muted/30 p-0">
          {sources.isLoading ? (
            <div className="flex flex-col gap-1.5 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : sources.isError ? (
            <div className="p-4"><ErrorState message={extractErrorMessage(sources.error)} /></div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-left text-[11px] font-medium text-muted-foreground">
                  <th className="py-2 pl-4 pr-3 font-medium">Source</th>
                  <th className="py-2 pr-3 font-medium">Enabled</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Last ingested</th>
                  <th className="py-2 pr-3 font-medium">Chunks</th>
                  <th className="py-2 pr-3 font-medium">Last run</th>
                  <th className="py-2 pr-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sources.data!.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-3 pl-4 text-[12px] text-muted-foreground">
                      No sources. Add one below.
                    </td>
                  </tr>
                ) : (
                  sources.data!.map((s) => (
                    <SourceTableRow
                      key={s.source_id} s={s} slug={slug}
                      onToggle={(sourceId, enabled) => toggleMutation.mutate({ sourceId, enabled })}
                      onIngest={(sourceId) => ingestMutation.mutate(sourceId)}
                      onDelete={(sourceId) => deleteMutation.mutate(sourceId)}
                      toggleLoading={toggleMutation.isPending && toggleMutation.variables?.sourceId === s.source_id}
                      ingestLoading={ingestMutation.isPending && ingestMutation.variables === s.source_id}
                      deleteLoading={deleteMutation.isPending && deleteMutation.variables === s.source_id}
                    />
                  ))
                )}
                <tr>
                  <td colSpan={7} className="px-4 py-2">
                    <Button variant="secondary" size="sm" className="h-7 text-[12px]"
                      onClick={() => setShowAddModal(true)}>
                      <i className="ti ti-plus text-[11px] mr-1" /> Add source
                    </Button>
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </TableCell>
      </TableRow>
      {showAddModal && (
        <AddSourceModal slug={slug} usedTypes={usedTypes} onClose={() => setShowAddModal(false)} />
      )}
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/admin/src/features/SourcesRow.tsx
git commit -m "feat(ui): SourcesRow uses source_id, shows name, delegates add to AddSourceModal"
```

---

## Task 10: Rebuild Containers + Smoke Test

- [ ] **Step 1: Rebuild API + worker with new deps**

```bash
docker compose build app worker
docker compose up -d app worker
```

- [ ] **Step 2: Run migration**

```bash
docker compose exec app alembic upgrade head
```

Expected: `Running upgrade 0009 -> 0010`

- [ ] **Step 3: Run backend tests**

```bash
docker compose exec app pytest tests/test_webpage_adapter.py tests/test_rest_endpoint_adapter.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Smoke test API via curl**

```bash
# Get an auth cookie first (replace email/password with valid dev credentials)
curl -s -c /tmp/c.txt -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"mrabir.ahamed@gmail.com","password":"YOUR_PASSWORD"}'

# Add a webpage source
curl -s -b /tmp/c.txt -X POST http://localhost:8000/api/v1/admin/plugins/author-profile-blocks/sources \
  -H "Content-Type: application/json" \
  -d '{"source_type":"webpage","name":"APB Docs","config":{"url":"https://docs.example.com/","max_depth":1}}'
```

Expected: `{"source_id":"...","name":"APB Docs","source_type":"webpage",...}`

- [ ] **Step 5: Build admin frontend**

```bash
docker compose build admin
docker compose up -d admin
```

- [ ] **Step 6: Verify UI**

Open http://localhost:8081, navigate to a plugin, expand sources. Confirm:
- "Add source" button opens the modal
- Type picker shows all types including webpage and rest_endpoint
- Clicking a github/wporg type adds immediately
- Clicking webpage shows the config form
- Existing sources show their name label

- [ ] **Step 7: Final commit tag**

```bash
git tag v-webpage-rest-sources
```

---

## Self-Review Checklist

- [x] **Migration** covers: add name column, backfill, NOT NULL, drop old constraint, add new constraint, expand check
- [x] **Model** SOURCE_TYPES and constraint match migration exactly
- [x] **Schemas** SourceSummary has `name`; AddSourceRequest has `name + config`; PatchConfigRequest defined
- [x] **Routes** `_get_source_by_id_or_404` used in all three changed routes (patch, delete, ingest-single); `uuid` imported
- [x] **Adapters** both implement `handles`, `fetch()`, use `build_client`, yield `RawDocument`
- [x] **Tasks** both adapters registered in `_ADAPTERS`
- [x] **Frontend types** `name: string` in SourceSummary; SOURCE_TYPES expanded
- [x] **API client** all four source functions use `sourceId`; `patchSourceConfig` added
- [x] **SourcesRow** imports `AddSourceModal`; mutations use `source_id`; edit button for configurable types
- [x] **AddSourceModal** single-instance types add immediately; multi-instance go to config form; `buildRestConfig` maps all pagination modes

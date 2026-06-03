# Custom Adapter Plugin System — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow internal developers and third-party companies to package custom ingestion adapters and install them into wp-support-rag without modifying core code.

**Architecture:** A startup-time `AdapterRegistry` singleton discovers built-in, pip entry-point, and file-drop adapters; upserts DB metadata rows; and replaces the static `_ADAPTERS` dict in `tasks.py`. Source type validation moves from a DB CHECK constraint to app-layer registry lookup.

**Tech Stack:** Python `importlib.metadata` entry points, FastAPI lifespan, SQLAlchemy 2.0 async, Alembic migration, React + TanStack Query, dynamic JSON Schema form renderer.

---

## 1. Constraints & Trust Model

- Adapters run as trusted code in the same process — no sandboxing.
- Two install paths: `.py` file upload via admin UI (simple adapters, no extra deps) and pip package via entry points (complex adapters with dependencies).
- Container restart required to activate newly installed adapters in both the API and Celery worker processes.
- File upload provides immediate validation feedback (import + protocol check) before restart.

---

## 2. Database Changes (Migration 0011)

### 2a. Drop `sources_source_type_check`

The existing CHECK constraint on `sources.source_type` is dropped. Validation moves to the app layer via `AdapterRegistry.all_handles()`.

```sql
ALTER TABLE sources DROP CONSTRAINT sources_source_type_check;
```

### 2b. New table: `adapter_plugins`

```sql
CREATE TABLE adapter_plugins (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         TEXT        NOT NULL UNIQUE,
    display_name TEXT        NOT NULL,
    version      TEXT,
    source       TEXT        NOT NULL CHECK (source IN ('builtin', 'entrypoint', 'file')),
    entry_point  TEXT,
    filename     TEXT,
    handles      TEXT[]      NOT NULL,
    config_schema JSONB      NOT NULL DEFAULT '{}',
    status       TEXT        NOT NULL DEFAULT 'loaded'
                             CHECK (status IN ('loaded', 'error', 'disabled')),
    error        TEXT,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Field notes:**
- `slug` — machine identifier, e.g. `acme.salesforce`. Built-ins use `builtin.<adapter_name>`.
- `handles` — source type strings this adapter owns, e.g. `["salesforce_kb", "salesforce_cases"]`.
- `config_schema` — JSON Schema object. Empty `{}` means the UI renders a raw JSON textarea.
- `source` — `builtin` (core adapters), `entrypoint` (pip-installed), `file` (uploaded `.py`).
- `entry_point` — e.g. `acme_wp_rag.adapter:SalesforceAdapter` (entrypoint adapters only).
- `filename` — e.g. `my_adapter.py` (file adapters only).

### 2c. Config setting

`CUSTOM_ADAPTERS_DIR: str = "/app/custom_adapters"` added to `app/config.py`. Empty string disables file-drop scanning. Volume-mounted in `docker-compose.yml`.

---

## 3. AdapterRegistry

### 3a. New file: `app/ingestion/adapter_registry.py`

```python
class AdapterTypeInfo(BaseModel):
    source_type: str
    display_name: str
    adapter_slug: str
    config_schema: dict
    is_builtin: bool
    multi_instance: bool   # True for all custom types; False for single-instance builtins

class AdapterRegistry:
    def get(self, source_type: str) -> SourceAdapter:
        """Return adapter for source_type. Raises KeyError if unknown."""

    def all_handles(self) -> frozenset[str]:
        """All registered source type strings."""

    def types_with_schema(self) -> list[AdapterTypeInfo]:
        """Ordered list of all available types with their config schemas."""

async def build_registry(session: AsyncSession) -> AdapterRegistry:
    """
    Startup entry point. Loads adapters in order:
      1. Built-ins (GitHub, WpOrg, Webpage, RestEndpoint)
      2. Entry points: importlib.metadata.entry_points(group="wp_support_rag.adapters")
      3. File-drop: *.py files in CUSTOM_ADAPTERS_DIR
    Upserts adapter_plugins rows for each. Returns populated registry.
    """
```

**Loading order and conflicts**: Built-ins load first and own their type strings permanently. If an entry-point or file adapter claims a type string already owned by a built-in, that adapter gets `status='error'` with message `"conflicts with built-in type: {type}"`. Conflicts between two custom adapters: first loaded wins, second gets error status. No silent overwrites.

**Global singleton** in `app/main.py` lifespan:
```python
adapter_registry: AdapterRegistry  # module-level, set in lifespan startup
```

Celery worker initializes its own registry instance at module import time (synchronous startup via `asyncio.run(build_registry(...))`).

### 3b. Single-instance built-in types

`AdapterTypeInfo.multi_instance = False` for: `github_readme`, `github_changelog`, `github_docs`, `github_issues`, `wporg_faq`, `wporg_changelog`, `wporg_support`. All custom adapter types default to `multi_instance = True`. `webpage` and `rest_endpoint` are also `multi_instance = True`.

Custom adapters may declare `multi_instance: ClassVar[bool] = False` to override.

---

## 4. Developer Contract

### 4a. Adapter class

```python
from typing import ClassVar, AsyncIterator

class MyAdapter:
    handles: ClassVar[tuple[str, ...]] = ("my_source_type",)
    display_name: ClassVar[str] = "My Source"          # shown in admin UI
    config_schema: ClassVar[dict] = {                  # optional; {} = raw JSON editor
        "type": "object",
        "properties": {
            "url": {"type": "string", "title": "Source URL", "format": "uri"},
            "api_key": {"type": "string", "title": "API Key"},
        },
        "required": ["url"],
    }
    multi_instance: ClassVar[bool] = True              # optional; defaults True

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        config = ctx.config
        ...
        yield RawDocument(
            external_id="unique-id",
            title="Document Title",
            doc_type="my_source_type",
            content="...",
            content_type="text",   # or "markdown" or "html"
            source_url="https://...",
        )
```

**Protocol validation** (checked at upload/load time):
- Class has `handles` attribute: non-empty `tuple[str, ...]`
- Class has `fetch` method: async generator
- `handles` values are non-empty strings, no spaces, no reserved built-in type conflicts

### 4b. Entry point packaging (`pyproject.toml`)

```toml
[project.entry-points."wp_support_rag.adapters"]
my_adapter = "my_package.adapter:MyAdapter"
```

Multiple adapters from one package:
```toml
[project.entry-points."wp_support_rag.adapters"]
salesforce_kb    = "acme_wp_rag.adapters.salesforce:SalesforceKBAdapter"
salesforce_cases = "acme_wp_rag.adapters.salesforce:SalesforceCasesAdapter"
```

### 4c. SDK package (`wp_support_rag_sdk`)

Standalone PyPI package at `packages/wp_support_rag_sdk/` in the monorepo. It contains the canonical definitions of the adapter interface — **not re-exports from `app.*`** (which would require the full app to be installed):

```
packages/wp_support_rag_sdk/
  wp_support_rag_sdk/
    __init__.py        # exports SourceAdapter, SourceContext, RawDocument, SourceFetchError, ContentType
    adapter.py         # SourceAdapter Protocol + RawDocument + SourceContext (copied/moved from app/ingestion/adapters/base.py)
  pyproject.toml
```

`app/ingestion/adapters/base.py` is updated to import from `wp_support_rag_sdk` rather than defining its own copies, so both the app and external adapters share the same type definitions.

External developers: `pip install wp_support_rag_sdk` — no app dependency.

### 4d. File-based adapter requirements

- Single `.py` file (no subdirectories, no relative imports)
- All dependencies must already be installed in the container
- Must contain at least one class satisfying the adapter protocol

---

## 5. API Routes

All routes require admin authentication. Added to `apps/api/app/api/routes_admin.py` (or a new `routes_adapters.py`).

### `GET /api/v1/admin/adapter-plugins`

Returns `list[AdapterPluginSummary]`:
```json
[
  {
    "slug": "builtin.github",
    "display_name": "GitHub",
    "version": null,
    "source": "builtin",
    "handles": ["github_readme", "github_changelog", "github_docs", "github_issues"],
    "status": "loaded",
    "error": null,
    "installed_at": "2026-06-03T10:00:00Z"
  }
]
```

### `GET /api/v1/admin/adapter-plugins/types`

Returns `list[AdapterTypeInfo]` — consumed by `AddSourceModal`. Ordered: built-ins first, then custom alphabetically.

### `POST /api/v1/admin/adapter-plugins/upload`

- Content-Type: `multipart/form-data`, field: `file` (`.py` extension required)
- Saves to `CUSTOM_ADAPTERS_DIR/{filename}`
- Immediately imports and validates the file
- Upserts `adapter_plugins` row with `status='loaded'` or `status='error'`
- Returns `AdapterPluginSummary`
- `409 Conflict` if any claimed `handles` type already belongs to a loaded adapter
- `422` if file extension is not `.py`
- Successful upload with `status='error'` returns HTTP 200 (file saved but broken) — error surfaced in response body

### `DELETE /api/v1/admin/adapter-plugins/{slug}`

- `403 Forbidden` if `source != 'file'`
- Deletes file from `CUSTOM_ADAPTERS_DIR`
- Deletes `adapter_plugins` row
- Returns 204
- Existing `sources` rows with that `source_type` are left intact; ingest attempts will fail with `KeyError` caught as a run error

### Existing route change

`POST /api/v1/admin/plugins/{slug}/sources`: replaces `source_type in SOURCE_TYPES` check with `source_type in adapter_registry.all_handles()`. Returns `400 Bad Request` for unknown types.

`registry.py` `add_source()`: same change — remove `SOURCE_TYPES` check, accept any type the registry knows.

---

## 6. Frontend

### 6a. New page: Adapters (`/adapters`)

Nav entry: between Sources and Settings (or under Settings sub-nav — implementer decides based on existing nav structure).

**Table columns:** Name | Handles | Source | Version | Status | Actions

**Row behaviour:**
- `builtin`: no delete, status badge always green
- `entrypoint`: no delete, version from package metadata
- `file`: delete button with confirm dialog

**Upload flow:**
1. "Upload Adapter" button top-right → file picker (`.py` only)
2. POST to `/adapter-plugins/upload`
3. Success: row appears in table with status badge
4. Error (validation failed): row appears with red "Error" badge + expandable error message
5. Info banner: "Restart required to activate newly installed adapters"

**Status badges:**
- `loaded` → green "Loaded"
- `error` → red "Error" (expandable tooltip with `error` field)
- `disabled` → grey "Disabled"

### 6b. `AddSourceModal` changes

Replace hardcoded `SOURCE_TYPES` and `MULTI_INSTANCE_TYPES` with API-driven data:

```ts
const { data: adapterTypes } = useQuery({
  queryKey: ["adapter-types"],
  queryFn: () => getAdapterTypes(),
  staleTime: 60_000,
})
```

- Type picker grid: built-in types render as before with existing labels/icons; custom types show `display_name` + a muted `source_type` badge
- `multi_instance` from `AdapterTypeInfo` drives whether clicking a type goes straight to add or opens the config step
- Config step: built-in types keep `WebpageConfigForm` / `RestConfigForm`; custom types render `JsonSchemaForm`

### 6c. `JsonSchemaForm` component

New component at `apps/admin/src/components/JsonSchemaForm.tsx`.

Renders fields from a JSON Schema `properties` object:

| JSON Schema | UI control |
|-------------|------------|
| `type: string` | `<input type="text">` |
| `type: string`, `format: uri` | `<input type="url">` |
| `type: string`, `enum: [...]` | `<select>` |
| `type: boolean` | toggle (reuse `EnableToggle` pattern) |
| `type: integer` or `number` | `<input type="number">` |
| `type: string`, `format: password` | `<input type="password">` |
| schema is `{}` or missing | raw JSON `<textarea>` |

- Required fields (in `required` array) get `*` label suffix
- `title` from property used as label; falls back to property key
- `description` from property rendered as muted help text below input
- Form output: plain `Record<string, unknown>` passed as `config` to `addSource()`

### 6d. `admin.ts` additions

```ts
export async function getAdapterTypes(): Promise<AdapterTypeInfo[]>
export async function listAdapterPlugins(): Promise<AdapterPluginSummary[]>
export async function uploadAdapterPlugin(file: File): Promise<AdapterPluginSummary>
export async function deleteAdapterPlugin(slug: string): Promise<void>
```

### 6e. `api.ts` type additions

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
  status: "loaded" | "error" | "disabled"
  error: string | null
  installed_at: string
}
```

---

## 7. Files Created / Modified

### New files
- `apps/api/app/ingestion/adapter_registry.py` — `AdapterRegistry`, `AdapterTypeInfo`, `build_registry()`
- `apps/api/app/api/routes_adapters.py` — all `/adapter-plugins` routes
- `apps/api/app/db/migrations/versions/20260603_0011_custom_adapter_plugins.py`
- `packages/wp_support_rag_sdk/wp_support_rag_sdk/adapter.py` — canonical SourceAdapter, SourceContext, RawDocument, SourceFetchError, ContentType definitions
- `packages/wp_support_rag_sdk/wp_support_rag_sdk/__init__.py` — re-exports from adapter.py
- `packages/wp_support_rag_sdk/pyproject.toml`
- `apps/admin/src/pages/AdaptersPage.tsx`
- `apps/admin/src/components/JsonSchemaForm.tsx`

### Modified files
- `apps/api/app/ingestion/adapters/base.py` — import types from `wp_support_rag_sdk` instead of defining them
- `apps/api/app/config.py` — add `CUSTOM_ADAPTERS_DIR`
- `apps/api/app/main.py` — lifespan: call `build_registry()`, store singleton
- `apps/api/app/ingestion/tasks.py` — replace `_ADAPTERS` with `adapter_registry`
- `apps/api/app/ingestion/registry.py` — replace `SOURCE_TYPES` check in `add_source()`
- `apps/api/app/api/routes_admin.py` — update source type validation, include adapter routes
- `apps/api/app/api/schemas.py` — add `AdapterPluginSummary`, `AdapterTypeInfo` schemas
- `apps/api/app/db/models.py` — remove `SOURCE_TYPES` from constraint (kept as reference tuple)
- `docker-compose.yml` — add `custom_adapters` volume mount on `app` and `worker`
- `apps/admin/src/types/api.ts` — add `AdapterTypeInfo`, `AdapterPluginSummary`
- `apps/admin/src/api/admin.ts` — add adapter API functions
- `apps/admin/src/features/AddSourceModal.tsx` — API-driven types, `JsonSchemaForm` for custom
- `apps/admin/src/App.tsx` (or router file) — add `/adapters` route
- `apps/admin/src/components/Sidebar.tsx` (or nav file) — add Adapters nav entry

---

## 8. Testing

- `tests/test_adapter_registry.py` — load built-ins, load from mock entry points, load from temp `.py` file, conflict detection
- `tests/test_routes_adapters.py` — list, upload valid file, upload invalid file (422/200+error), delete file adapter, delete builtin (403)
- `JsonSchemaForm` — unit tested with schema fixtures covering all field types
- Existing tests unchanged (built-in adapters still resolve correctly through registry)

# Webpage & REST Endpoint Source Types — Design Spec

Date: 2026-06-03  
Author: Al Amin Ahamed

## Summary

Add two new ingestion source types (`webpage`, `rest_endpoint`) that allow plugins to crawl arbitrary web pages and consume paginated REST APIs. Alongside this, relax the one-source-per-type constraint so a plugin can have multiple sources of the same type (e.g. three different docs sites as three `webpage` sources).

---

## 1. Database Changes

### 1.1 `Source.name` column

Add a non-nullable `name: str` column to the `sources` table.

- For **single-instance types** (`github_*`, `wporg_*`): name = source_type, set automatically by the API, not user-editable.
- For **multi-instance types** (`webpage`, `rest_endpoint`): name is user-provided (required), defaults to URL hostname if omitted.

### 1.2 Unique constraint change

- **Drop:** `UNIQUE(plugin_id, source_type)`
- **Add:** `UNIQUE(plugin_id, name)`

This allows multiple `webpage` sources per plugin as long as each has a distinct name.

### 1.3 SOURCE_TYPES expansion

Add `"webpage"` and `"rest_endpoint"` to:
- DB check constraint on `source_type`
- `SOURCE_TYPES` tuple in `app/db/models.py`
- `SOURCE_TYPES` constant in `apps/admin/src/types/api.ts`

### 1.4 Migration `0010`

Steps:
1. Add `name VARCHAR NOT NULL DEFAULT ''` (temporary default)
2. `UPDATE sources SET name = source_type`
3. Remove temporary default
4. Drop `UNIQUE(plugin_id, source_type)`
5. Add `UNIQUE(plugin_id, name)`
6. Extend `source_type` check constraint to include `webpage` and `rest_endpoint`

---

## 2. Backend Adapters

### 2.1 `WebpageAdapter`

**File:** `app/ingestion/adapters/webpage.py`  
**Class:** `WebpageAdapter`  
**Handles:** `("webpage",)`  
**New deps:** `beautifulsoup4`, `lxml`

**Config fields** (stored in `Source.config` JSONB):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | str | required | Start URL |
| `max_depth` | int | 2 | Crawl depth 1–5 |
| `selector` | str | `"main,article,[role=main],body"` | CSS selector for content extraction |
| `url_filter` | str | same-domain regex | Regex; only follow matching links |

**Crawl algorithm:**
- BFS from `url`, set of visited URLs, queue of `(url, depth)` pairs
- For each page: fetch with `httpx`, parse with BeautifulSoup, extract text from `selector`
- Follow `<a href>` links that match `url_filter` and depth < `max_depth`
- Yield one `RawDocument` per page: `external_id=url`, `content_type="html"`
- Respect `polite_delay_seconds` between requests
- Skip non-200 responses (log warning, continue crawl)

### 2.2 `RestEndpointAdapter`

**File:** `app/ingestion/adapters/rest_endpoint.py`  
**Class:** `RestEndpointAdapter`  
**Handles:** `("rest_endpoint",)`

**Config fields:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | str | required | Base endpoint URL |
| `method` | str | `"GET"` | HTTP method (GET or POST) |
| `headers` | dict | `{}` | Static headers (auth, content-type, etc.) |
| `query_params` | dict | `{}` | Extra query parameters |
| `pagination` | str | `"none"` | `"none"` \| `"page_param"` \| `"link_header"` \| `"cursor"` |
| `page_param` | str | `"page"` | Query param for page number |
| `page_size_param` | str | `"per_page"` | Query param for page size |
| `page_size` | int | `100` | Items per page |
| `cursor_field` | str | — | JSON field name holding next cursor |
| `items_path` | str | — | Dot-path to array in response (e.g. `"data"`, `"results"`); omit for root array |
| `id_field` | str | required | Item field for `external_id` |
| `content_field` | str | required | Item field for document body text |
| `title_field` | str | — | Item field for document title |
| `url_field` | str | — | Item field for `source_url` |

**Pagination behaviour:**
- `none`: single request, response is the array (or root object with `items_path`)
- `page_param`: increment page until empty array returned
- `link_header`: follow `Link: <url>; rel="next"` until absent
- `cursor`: use `cursor_field` value as next page cursor param until null/absent

Each item maps to one `RawDocument`: `content_type="text"`.

**Adapter registration** (`tasks.py`):
```python
_WEBPAGE_ADAPTER = WebpageAdapter()
_REST_ADAPTER = RestEndpointAdapter()
_ADAPTERS = {
    **dict.fromkeys(_GITHUB_ADAPTER.handles, _GITHUB_ADAPTER),
    **dict.fromkeys(_WPORG_ADAPTER.handles, _WPORG_ADAPTER),
    **dict.fromkeys(_WEBPAGE_ADAPTER.handles, _WEBPAGE_ADAPTER),
    **dict.fromkeys(_REST_ADAPTER.handles, _REST_ADAPTER),
}
```

---

## 3. API Changes

### 3.1 Route parameter change

Delete/patch/ingest-single routes switch from `{source_type}` to `{source_id}` (UUID):

```
GET    /api/v1/admin/plugins/{slug}/sources                    (unchanged)
POST   /api/v1/admin/plugins/{slug}/sources                    (updated request body)
PATCH  /api/v1/admin/plugins/{slug}/sources/{source_id}        (was {source_type})
DELETE /api/v1/admin/plugins/{slug}/sources/{source_id}        (was {source_type})
PATCH  /api/v1/admin/plugins/{slug}/sources/{source_id}/config (new)
POST   /api/v1/admin/ingest/{slug}/sources/{source_id}         (was /ingest/{slug}/{source_type})
```

The old `/ingest/{slug}/{source_type}` route is kept as a deprecated alias during transition.

### 3.2 Schema changes

**`AddSourceRequest`** (updated):
```python
class AddSourceRequest(BaseModel):
    source_type: str
    name: str | None = None   # required for webpage/rest_endpoint; auto-set for others
    config: dict[str, Any] = {}
```

Server validates:
- `webpage`: `url` required and valid URL, `max_depth` 1–5
- `rest_endpoint`: `url` required, `content_field` required, `id_field` required, `pagination` one of four values

**`PatchConfigRequest`** (new):
```python
class PatchConfigRequest(BaseModel):
    config: dict[str, Any]
```

**`SourceSummary`** (updated):
```python
class SourceSummary(BaseModel):
    source_id: str
    name: str           # new
    source_type: str
    enabled: bool
    ...
```

---

## 4. Frontend Changes

### 4.1 `types/api.ts`

- Add `"webpage"` and `"rest_endpoint"` to `SOURCE_TYPES`
- Add `name: string` to `SourceSummary`

### 4.2 `api/admin.ts`

- `patchSource(slug, sourceId, payload)` — switch param from source_type to source_id
- `deleteSource(slug, sourceId)` — switch param
- `ingestSource(slug, sourceId)` — switch param
- `patchSourceConfig(slug, sourceId, config)` — new

### 4.3 `SourcesRow.tsx` changes

- Display `source.name` as primary label; `source.source_type` as muted badge
- All mutations use `source.source_id` (UUID)
- Show "Edit config" icon button for `webpage` and `rest_endpoint` sources

### 4.4 Add Source modal (two-step)

**Step 1:** Source type picker (grid of buttons with icons)
- `github_*` / `wporg_*` types: click → immediately add (no config form needed)
- `webpage` / `rest_endpoint`: click → go to Step 2

**Step 2:** Config form (type-specific)

**`WebpageConfigForm`:**
- Name (text, required, auto-fills from URL hostname on blur)
- URL (text, required)
- Max depth (select 1–5, default 2)
- CSS selector (text, optional, placeholder shown)
- URL filter regex (text, optional)

**`RestEndpointConfigForm`:**
- Name (text, required)
- URL (text, required)
- Method (GET / POST toggle)
- Auth section: dropdown (None / Bearer token / API key header / Custom headers)
  - Bearer: single token input
  - API key: header name + value inputs
  - Custom: key-value pairs list
- Content field (text, required)
- Title field (text, optional)
- URL field (text, optional)
- ID field (text, required)
- Pagination type (None / Page param / Link header / Cursor)
  - Page param: page param name, size param name, size
  - Cursor: cursor field name
- Items path (text, optional, e.g. `data.results`)
- Advanced: collapsible raw JSON editor (full config override)

### 4.5 Edit Config modal

Same form as Step 2 above, pre-populated with current `source.config`. Used for editing existing `webpage`/`rest_endpoint` sources.

---

## 5. New Dependencies

`pyproject.toml` additions:
```
"beautifulsoup4>=4.12",
"lxml>=5.0",
```

---

## 6. Files to Create

| File | Purpose |
|------|---------|
| `app/ingestion/adapters/webpage.py` | WebpageAdapter |
| `app/ingestion/adapters/rest_endpoint.py` | RestEndpointAdapter |
| `app/db/migrations/versions/20260603_0010_webpage_rest_sources.py` | DB migration |
| `apps/admin/src/features/SourceConfigModal.tsx` | Shared config modal shell |
| `apps/admin/src/features/WebpageConfigForm.tsx` | Webpage config form |
| `apps/admin/src/features/RestEndpointConfigForm.tsx` | REST endpoint config form |

## 7. Files to Modify

| File | Change |
|------|--------|
| `app/db/models.py` | Add `name` to Source, expand SOURCE_TYPES |
| `app/api/schemas.py` | Update AddSourceRequest, SourceSummary; add PatchConfigRequest |
| `app/api/routes_admin.py` | Update route params, add config patch endpoint |
| `app/ingestion/tasks.py` | Register new adapters |
| `pyproject.toml` | Add beautifulsoup4, lxml |
| `apps/admin/src/types/api.ts` | Add name, expand SOURCE_TYPES |
| `apps/admin/src/api/admin.ts` | Update source mutations to use source_id |
| `apps/admin/src/features/SourcesRow.tsx` | Display name, use source_id, add edit button |

# Setup Wizard Design

**Goal:** A first-run setup wizard that gates access to the admin until generation provider, embeddings, and the first plugin are configured.

**Architecture:** Dedicated `/setup` route outside AppShell, driven by a persistent `system_settings` DB table. `RequireAuth` enforces the gate — incomplete setup redirects to `/setup`; completed setup redirects away from it. Completion signals via router state to show a dashboard banner.

**Tech Stack:** React Router nested routes, React Query, existing shadcn components, FastAPI + SQLAlchemy, Alembic migration.

---

## Backend

### Database

New table `system_settings`:

| column | type | notes |
|---|---|---|
| `id` | `UUID` pk | |
| `key` | `TEXT` unique not null | |
| `value` | `TEXT` not null | |
| `updated_at` | `TIMESTAMPTZ` | auto-updated |

Seeded with no rows on migration. Row `key="setup_complete"` absent = not complete.

### API Routes

Both under `/api/v1/admin/` and require authenticated admin user.

**`GET /setup/status`**
- Permission: any authenticated admin (no specific permission required)
- Reads row where `key = "setup_complete"`
- Returns `{ "complete": true }` if row exists and `value = "true"`, else `{ "complete": false }`

**`POST /setup/complete`**
- Permission: `settings:write`
- Upserts row `key="setup_complete"`, `value="true"`
- Returns `{ "complete": true }`

### Migration

File: `apps/api/app/db/migrations/versions/20260601_0005_system_settings.py`

Creates `system_settings` table with `id`, `key`, `value`, `updated_at`.

---

## Frontend

### Route Structure

```
Root (AuthProvider)
├── /login                    public
├── /forgot-password          public
├── /reset-password           public
├── /accept-invite            public
├── /setup                    RequireAuth, no AppShell  ← new
└── /  (ProtectedShell)       RequireAuth + AppShell
    ├── /                     DashboardPage
    ├── /plugins
    ├── /playground
    ├── /users
    ├── /settings/*
    └── /profile/*
```

### Setup Guard in `RequireAuth`

After confirming user is authenticated, `RequireAuth` calls `getSetupStatus()`:
- `complete: false` and `pathname !== "/setup"` → `<Navigate to="/setup" replace />`
- `complete: true` and `pathname === "/setup"` → `<Navigate to="/" replace />`
- Otherwise render children normally

`getSetupStatus()` result is cached via React Query (`queryKey: ["setup-status"]`, `staleTime: Infinity`). After `completeSetup()` succeeds, invalidate `["setup-status"]`.

### New Files

- `apps/admin/src/pages/SetupWizardPage.tsx` — wizard page component
- `apps/admin/src/api/admin.ts` — add `getSetupStatus()` and `completeSetup()`

### Modified Files

- `apps/admin/src/app/routes.tsx` — add `/setup` route
- `apps/admin/src/lib/auth.tsx` — add setup status check to `RequireAuth`
- `apps/admin/src/pages/DashboardPage.tsx` — add setup complete banner

---

## Wizard Page Layout

Full-page layout matching `AuthLayout` visual language:
- Navy left panel (`var(--nav)`) with logo, product name, and step list summary
- White right panel with step content
- No sidebar, no topbar

### Step Progress Indicator

Horizontal stepper at top of right panel: numbered circles `① → ② → ③` connected by a line. Active step: indigo filled circle. Completed step: indigo with checkmark. Upcoming: gray outline.

---

## Wizard Steps

### Step 1 — Generation Provider

Fields (same data as `GenerationSection` in `SettingsPage`):
- Provider `<Select>`: `anthropic` / `openai` / `ollama`
- Conditional field:
  - anthropic → "Anthropic API key" password input
  - openai → "OpenAI API key" password input
  - ollama → "Ollama base URL" text input (default `http://localhost:11434`)
- Model text input with datalist (auto-populated for ollama if reachable)

On "Next": calls `updateLlmConfig({ provider, model })`. If resolves → advance to step 2. On error → show inline error, stay on step 1.

### Step 2 — Embeddings

Fields (same data as `EmbeddingSection` in `SettingsPage`):
- Provider `<Select>`: `openai` / `ollama`
- Model text input with datalist

On "Next": calls `updateEmbeddingConfig({ provider, model })`. Fires `ingestAll()` as fire-and-forget (no await, errors ignored). If `updateEmbeddingConfig` resolves → advance to step 3.

### Step 3 — First Plugin

Fields (same as `RegisterPluginModal`):
- Plugin slug (required)
- GitHub repository URL (optional)
- WordPress.org plugin URL (optional)

On "Finish":
1. `registerPlugin({ slug, github_url, wporg_url })` — await, show error inline if fails
2. `ingestPlugin(slug)` — fire-and-forget
3. `completeSetup()` — await
4. Invalidate `["setup-status"]` query
5. `navigate("/", { replace: true, state: { setupComplete: true } })`

### Navigation

- "Back" button on steps 2 and 3 — returns to previous step, preserves entered values in local component state
- No "Skip" button — hard gate

---

## Setup Complete Banner

Location: `DashboardPage`, rendered above the stats grid.

Trigger: `useLocation().state?.setupComplete === true`

Content:
```
✓  Setup complete — generation, embeddings, and your first plugin are configured.
   Ingestion is running in the background.                                    [×]
```

Styling: full-width indigo-tinted banner (`bg-accent border border-primary/20`), indigo `ti-circle-check` icon, `×` dismiss button.

Dismiss behavior:
- Sets `localStorage("setup-banner-dismissed", "true")`
- Also hidden if that key exists on mount
- On mount: `navigate(".", { replace: true, state: {} })` to clear router state (prevents re-show on back navigation)

---

## Error States

- Steps 1 and 2: API call failure shows inline error below the form, "Next" re-enabled
- Step 3 `registerPlugin` failure: inline error, "Finish" re-enabled
- Step 3 `completeSetup` failure: inline error with "Retry" — does not re-register the plugin
- `getSetupStatus` network failure in `RequireAuth`: fail open (render children, don't block access)

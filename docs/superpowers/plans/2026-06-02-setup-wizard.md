# Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A first-run setup wizard at `/setup` that gates admin access until generation provider, embeddings, and the first plugin are configured, driven by a `system_settings` DB table.

**Architecture:** Backend adds a `system_settings` table + two routes (`GET/POST /api/v1/admin/setup/*`). Frontend adds a setup guard to `RequireAuth` that redirects to `/setup` when incomplete; the wizard is a full-page 3-step form outside `AppShell`; dashboard shows a dismissible "setup complete" banner after redirect.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, React, React Router, TanStack Query, Tabler Icons.

---

## File map

**Create:**
- `apps/api/app/db/migrations/versions/20260602_0005_system_settings.py` — Alembic migration
- `apps/api/app/api/routes_setup.py` — GET /setup/status + POST /setup/complete
- `apps/api/tests/test_setup.py` — 4 backend tests
- `apps/admin/src/pages/SetupWizardPage.tsx` — full wizard page

**Modify:**
- `apps/api/app/db/models.py` — add `SystemSetting` model class
- `apps/api/app/api/schemas.py` — add `SetupStatusResponse`
- `apps/api/app/api/deps.py` — add `require_any_admin` dependency
- `apps/api/app/main.py` — register setup router
- `apps/admin/src/api/admin.ts` — add `getSetupStatus`, `completeSetup`
- `apps/admin/src/lib/auth.tsx` — setup guard in `RequireAuth`
- `apps/admin/src/app/routes.tsx` — add `/setup` route
- `apps/admin/src/pages/DashboardPage.tsx` — `SetupCompleteBanner`

---

## Task 1: Backend — `SystemSetting` model + migration

**Files:**
- Modify: `apps/api/app/db/models.py` (after line 627, after `PasswordResetToken` class)
- Create: `apps/api/app/db/migrations/versions/20260602_0005_system_settings.py`

- [ ] **Step 1: Add `SystemSetting` to `apps/api/app/db/models.py`**

Open the file and append after the `PasswordResetToken` class (at the end of the file):

```python
class SystemSetting(Base):
    """Key-value system settings persisted in the database."""

    __tablename__ = "system_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: Create the Alembic migration**

Create `apps/api/app/db/migrations/versions/20260602_0005_system_settings.py`:

```python
"""Add system_settings table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-02

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
```

- [ ] **Step 3: Apply the migration**

```bash
cd apps/api
uv run alembic upgrade head
```

Expected output ends with: `Running upgrade 0004 -> 0005, Add system_settings table`

- [ ] **Step 4: Verify the table exists**

```bash
cd apps/api
uv run python -c "
import asyncio
from app.db.engine import get_sessionmaker
from sqlalchemy import text

async def check():
    async with get_sessionmaker()() as s:
        result = await s.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_name='system_settings'\"))
        print(result.scalar())

asyncio.run(check())
"
```

Expected: `system_settings`

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/db/models.py \
        apps/api/app/db/migrations/versions/20260602_0005_system_settings.py
git commit -m "feat(api): add SystemSetting model and migration"
```

---

## Task 2: Backend — schema + `require_any_admin` dep + setup routes

**Files:**
- Modify: `apps/api/app/api/schemas.py` (append at end)
- Modify: `apps/api/app/api/deps.py` (append after `require_permission`)
- Create: `apps/api/app/api/routes_setup.py`
- Modify: `apps/api/app/main.py` (add import + `include_router`)

- [ ] **Step 1: Add `SetupStatusResponse` to `apps/api/app/api/schemas.py`**

Append at the end of the file:

```python
class SetupStatusResponse(BaseModel):
    """Response for setup status and completion endpoints.

    Attributes:
        complete: Whether the first-run setup wizard has been completed.
    """

    complete: bool
```

- [ ] **Step 2: Add `require_any_admin` to `apps/api/app/api/deps.py`**

Append after the `require_permission` function (after line 187):

```python
async def require_any_admin(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
) -> UserClaims:
    """FastAPI dependency that validates the auth cookie without a specific permission.

    Args:
        request: The incoming request (for the cookie).
        settings: Application settings supplying the JWT secret.

    Returns:
        UserClaims: The decoded JWT claims.

    Raises:
        HTTPException: 401 when no valid cookie is present.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
        )
    return verify_jwt(token, secret=settings.jwt_secret.get_secret_value())
```

- [ ] **Step 3: Create `apps/api/app/api/routes_setup.py`**

```python
"""Setup wizard endpoints — first-run status and completion.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_any_admin, require_permission
from app.api.schemas import SetupStatusResponse
from app.auth.jwt import UserClaims
from app.db.engine import get_session
from app.db.models import SystemSetting

router = APIRouter(prefix="/api/v1/admin", tags=["setup"])

_KEY = "setup_complete"


@router.get("/setup/status", response_model=SetupStatusResponse)
async def get_setup_status(
    _: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Return whether the first-run setup wizard has been completed.

    Returns ``complete: false`` when the ``setup_complete`` key is absent or
    not ``"true"``, so a missing row is treated as incomplete.
    """
    row = await session.scalar(
        select(SystemSetting).where(SystemSetting.key == _KEY)
    )
    return SetupStatusResponse(complete=row is not None and row.value == "true")


@router.post("/setup/complete", response_model=SetupStatusResponse)
async def complete_setup(
    _: UserClaims = Depends(require_permission("settings:write")),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Mark the first-run setup wizard as complete.

    Upserts the ``setup_complete`` system setting so the call is idempotent.
    """
    stmt = (
        pg_insert(SystemSetting)
        .values(key=_KEY, value="true")
        .on_conflict_do_update(index_elements=["key"], set_={"value": "true"})
    )
    await session.execute(stmt)
    await session.commit()
    return SetupStatusResponse(complete=True)
```

- [ ] **Step 4: Register the setup router in `apps/api/app/main.py`**

Add the import alongside the existing router imports (around line 24):

```python
from app.api.routes_setup import router as setup_router
```

Add `include_router` call after line 143 (after `routes_admin.router`):

```python
    app.include_router(setup_router)
```

- [ ] **Step 5: Verify the routes appear in OpenAPI**

```bash
cd apps/api
uv run uvicorn app.main:create_app --factory --port 8001 &
sleep 2
curl -s http://localhost:8001/openapi.json | python3 -c "
import json,sys
paths = json.load(sys.stdin)['paths']
for p in paths:
    if 'setup' in p:
        print(p)
"
kill %1
```

Expected output:
```
/api/v1/admin/setup/status
/api/v1/admin/setup/complete
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schemas.py \
        apps/api/app/api/deps.py \
        apps/api/app/api/routes_setup.py \
        apps/api/app/main.py
git commit -m "feat(api): add setup status + complete routes"
```

---

## Task 3: Backend — tests

**Files:**
- Create: `apps/api/tests/test_setup.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_setup.py`:

```python
"""Tests for GET /api/v1/admin/setup/status and POST /api/v1/admin/setup/complete.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.deps import get_settings_dep
from app.auth.jwt import UserClaims, create_access_token
from app.config import Settings
from app.db.engine import dispose_engine, get_sessionmaker
from app.db.models import SystemSetting
from app.db.redis import close_redis, get_redis
from app.main import create_app

from tests.conftest import database_available

_JWT_SECRET = "test-jwt-secret"  # noqa: S105
_STATUS_URL = "/api/v1/admin/setup/status"
_COMPLETE_URL = "/api/v1/admin/setup/complete"


def _test_settings(**kwargs) -> Settings:
    return Settings(jwt_secret=_JWT_SECRET, bootstrap_email=None, bootstrap_password=None, **kwargs)


def _cookie(permissions: list[str]) -> dict[str, str]:
    claims = UserClaims(
        sub=str(uuid.uuid4()),
        email="admin@test.com",
        roles=["super_admin"],
        permissions=permissions,
    )
    token = create_access_token(claims, secret=_JWT_SECRET, ttl_seconds=300)
    return {"access_token": token}


async def _clear_system_settings() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(delete(SystemSetting))
        await session.commit()
    await dispose_engine()
    await close_redis()
    for cached in (get_sessionmaker,):
        cached.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _test_settings()
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def _ready() -> None:
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")
    await _clear_system_settings()


@pytest.mark.asyncio
async def test_get_setup_status_returns_false_when_no_row(_ready: None, client: TestClient) -> None:
    resp = client.get(_STATUS_URL, cookies=_cookie([]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": False}


@pytest.mark.asyncio
async def test_post_setup_complete_marks_complete(_ready: None, client: TestClient) -> None:
    resp = client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": True}

    # Subsequent GET reflects the change
    resp2 = client.get(_STATUS_URL, cookies=_cookie([]))
    assert resp2.status_code == 200
    assert resp2.json() == {"complete": True}


@pytest.mark.asyncio
async def test_post_setup_complete_is_idempotent(_ready: None, client: TestClient) -> None:
    client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    resp = client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": True}


@pytest.mark.asyncio
async def test_setup_complete_requires_settings_write(_ready: None, client: TestClient) -> None:
    resp = client.post(_COMPLETE_URL, cookies=_cookie([]))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_setup_status_requires_auth(client: TestClient) -> None:
    resp = client.get(_STATUS_URL)  # no cookie
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail (DB needed)**

```bash
cd apps/api
uv run pytest tests/test_setup.py -v 2>&1 | head -20
```

Expected: Either `SKIP` (no DB reachable) or `FAILED` with `ImportError` / `AttributeError` if routes not yet registered. If routes are registered from Task 2, tests should pass. Move on.

- [ ] **Step 3: Run full test suite to check no regressions**

```bash
cd apps/api
uv run pytest -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_setup.py
git commit -m "test(api): setup status and complete endpoint tests"
```

---

## Task 4: Frontend — API client functions

**Files:**
- Modify: `apps/admin/src/api/admin.ts` (append two functions)
- Modify: `apps/admin/src/types/api.ts` (append `SetupStatus` interface)

- [ ] **Step 1: Add `SetupStatus` to `apps/admin/src/types/api.ts`**

Append at the end of the file:

```typescript
export interface SetupStatus {
  complete: boolean;
}
```

- [ ] **Step 2: Add `getSetupStatus` and `completeSetup` to `apps/admin/src/api/admin.ts`**

Append at the end of `apps/admin/src/api/admin.ts`:

```typescript
export async function getSetupStatus(): Promise<SetupStatus> {
  const res = await apiClient.get<SetupStatus>("/api/v1/admin/setup/status");
  return res.data;
}

export async function completeSetup(): Promise<SetupStatus> {
  const res = await apiClient.post<SetupStatus>("/api/v1/admin/setup/complete");
  return res.data;
}
```

Also add `SetupStatus` to the import at the top of `admin.ts`:

```typescript
import type {
  Health,
  EmbeddingConfigUpdate,
  IngestAllResponse,
  IngestTriggerResponse,
  LLMConfig,
  LLMConfigUpdate,
  Metrics,
  OllamaModels,
  PluginRegistration,
  PluginSummary,
  RecentQuery,
  SetupStatus,
  SourceSummary,
} from "@/types/api";
```

- [ ] **Step 3: TypeScript check**

```bash
cd /path/to/repo-root
pnpm --filter @wp-support-rag/admin type-check
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/admin/src/types/api.ts apps/admin/src/api/admin.ts
git commit -m "feat(admin): add getSetupStatus and completeSetup API functions"
```

---

## Task 5: Frontend — `RequireAuth` setup guard

**Files:**
- Modify: `apps/admin/src/lib/auth.tsx`

The current `RequireAuth` only checks `user === null`. We add a React Query check for setup status and redirect to `/setup` when incomplete.

- [ ] **Step 1: Update imports in `apps/admin/src/lib/auth.tsx`**

Replace the current react-router-dom import line:
```typescript
import { useNavigate } from "react-router-dom";
```
With:
```typescript
import { Navigate, useLocation, useNavigate } from "react-router-dom";
```

Add TanStack Query import after the existing imports:
```typescript
import { useQuery } from "@tanstack/react-query";
import { getSetupStatus } from "@/api/admin";
```

- [ ] **Step 2: Replace `RequireAuth` in `apps/admin/src/lib/auth.tsx`**

Replace the entire `RequireAuth` function (lines 63–76) with:

```typescript
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const location = useLocation();

  const setupStatus = useQuery({
    queryKey: ["setup-status"],
    queryFn: getSetupStatus,
    enabled: !isLoading && user !== null,
    staleTime: Infinity,
    retry: false,
  });

  // Still loading auth or (auth ok but setup status pending) — render nothing
  if (isLoading || (!isLoading && user !== null && setupStatus.isPending)) return null;

  // Not logged in → login page
  if (user === null) return <Navigate to="/login" replace />;

  // Setup status loaded: enforce the gate
  // Fail open on network error (setupStatus.isError) — don't block access
  if (setupStatus.data !== undefined) {
    if (!setupStatus.data.complete && location.pathname !== "/setup") {
      return <Navigate to="/setup" replace />;
    }
    if (setupStatus.data.complete && location.pathname === "/setup") {
      return <Navigate to="/" replace />;
    }
  }

  return <>{children}</>;
}
```

- [ ] **Step 3: TypeScript check**

```bash
pnpm --filter @wp-support-rag/admin type-check
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/admin/src/lib/auth.tsx
git commit -m "feat(admin): RequireAuth — redirect to /setup when setup incomplete"
```

---

## Task 6: Frontend — `SetupWizardPage`

**Files:**
- Create: `apps/admin/src/pages/SetupWizardPage.tsx`

- [ ] **Step 1: Create `apps/admin/src/pages/SetupWizardPage.tsx`**

```typescript
// First-run setup wizard: generation → embeddings → first plugin. Author: Al Amin Ahamed.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  completeSetup,
  getLlmConfig,
  getOllamaModels,
  ingestAll,
  ingestPlugin,
  registerPlugin,
  updateEmbeddingConfig,
  updateLlmConfig,
} from "@/api/admin";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { extractErrorMessage } from "@/lib/queryClient";
import { cn } from "@/lib/utils";
import type { LLMConfig, OllamaModels } from "@/types/api";
import { SOURCE_TYPES } from "@/types/api";

type Step = 1 | 2 | 3;

const STEP_LABELS = ["Generation", "Embeddings", "First Plugin"];

// ---------------------------------------------------------------------------
// Stepper
// ---------------------------------------------------------------------------

function Stepper({ current }: { current: Step }) {
  return (
    <div className="flex items-center">
      {STEP_LABELS.map((label, i) => {
        const n = (i + 1) as Step;
        const done = n < current;
        const active = n === current;
        return (
          <div key={n} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex size-7 items-center justify-center rounded-full text-xs font-bold border-2 transition-colors",
                  done
                    ? "bg-primary border-primary text-white"
                    : active
                      ? "bg-primary/10 border-primary text-primary"
                      : "bg-muted border-muted-foreground/20 text-muted-foreground",
                )}
              >
                {done ? <i className="ti ti-check text-xs" /> : n}
              </div>
              <span
                className={cn(
                  "text-[10px] font-medium whitespace-nowrap",
                  active ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
            {i < STEP_LABELS.length - 1 && (
              <div
                className={cn(
                  "h-px flex-1 mx-2 mb-5 transition-colors",
                  done ? "bg-primary" : "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left panel
// ---------------------------------------------------------------------------

const STEP_SUMMARIES = [
  { icon: "ti-robot", text: "Choose your AI generation provider and model." },
  { icon: "ti-database", text: "Configure the embedding model for semantic search." },
  { icon: "ti-puzzle", text: "Register your first plugin to start ingesting docs." },
];

function LeftPanel({ step }: { step: Step }) {
  return (
    <div
      className="hidden lg:flex w-[360px] shrink-0 flex-col justify-between p-12 relative overflow-hidden"
      style={{ backgroundColor: "var(--nav)" }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="pointer-events-none absolute -top-32 -right-32 size-64 rounded-full bg-indigo-500/20 blur-3xl" />

      <div className="relative">
        <div className="flex items-center gap-2.5 mb-10">
          <Logo size={28} />
          <div>
            <div className="text-[13px] font-bold text-[#e0eaf8] tracking-tight leading-none">
              Support RAG
            </div>
            <div className="text-[9px] font-bold text-primary tracking-[1.5px] uppercase mt-1">
              Setup Wizard
            </div>
          </div>
        </div>

        <h1 className="text-2xl font-bold text-white leading-tight mb-2">
          Let's get you set up
        </h1>
        <p className="text-sm text-[#4b6284] leading-relaxed">
          Configure your AI providers and add your first plugin in three steps.
        </p>

        <div className="mt-8 space-y-4">
          {STEP_SUMMARIES.map(({ icon, text }, i) => {
            const n = i + 1;
            const done = n < step;
            const active = n === step;
            return (
              <div
                key={n}
                className={cn(
                  "flex items-start gap-3 transition-opacity",
                  !active && !done && "opacity-40",
                )}
              >
                <div
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full text-xs",
                    done
                      ? "bg-primary/30 text-primary"
                      : active
                        ? "bg-primary/20 text-primary"
                        : "bg-white/5 text-white/40",
                  )}
                >
                  {done ? (
                    <i className="ti ti-check text-xs" />
                  ) : (
                    <i className={`ti ${icon} text-xs`} />
                  )}
                </div>
                <span
                  className={cn(
                    "text-sm leading-relaxed pt-0.5",
                    active
                      ? "text-[#c8d8ed]"
                      : done
                        ? "text-[#4b6284]"
                        : "text-[#2e4060]",
                  )}
                >
                  {text}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <p className="relative text-[11px] text-[#2e4060]">
        You can change all of these settings later from the Settings page.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function ModelField({
  hint,
  value,
  onChange,
  placeholder,
  isOllama,
  listId,
  ollama,
}: {
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  isOllama: boolean;
  listId: string;
  ollama?: OllamaModels;
}) {
  return (
    <Field label="Model" hint={hint}>
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="font-mono text-[13px]"
        list={isOllama && ollama?.reachable ? listId : undefined}
      />
      {isOllama && ollama?.reachable && (
        <datalist id={listId}>
          {ollama.models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      )}
      {isOllama && ollama && !ollama.reachable && (
        <p className="mt-1 text-xs text-warning">
          Ollama unreachable at {ollama.base_url}
        </p>
      )}
    </Field>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <p className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <i className="ti ti-alert-circle shrink-0" /> {message}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Generation provider
// ---------------------------------------------------------------------------

function Step1Generation({
  config,
  ollama,
  provider,
  model,
  onProvider,
  onModel,
  error,
  pending,
  onNext,
}: {
  config: LLMConfig | undefined;
  ollama: OllamaModels | undefined;
  provider: string;
  model: string;
  onProvider: (p: string) => void;
  onModel: (m: string) => void;
  error: string | null;
  pending: boolean;
  onNext: () => void;
}) {
  const selected = config?.providers.find((p) => p.name === provider);

  if (!config) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Generation provider</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the AI model that will answer support questions.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Provider">
          <Select value={provider} onValueChange={onProvider}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {config.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                  {p.name === config.default_provider ? " (default)" : ""}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        {provider !== "ollama" && (
          <p className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <i className="ti ti-info-circle mr-1" />
            {provider === "anthropic" ? "Anthropic" : "OpenAI"} credentials are
            configured via{" "}
            <code className="font-mono">
              WPRAG_{provider.toUpperCase()}_API_KEY
            </code>{" "}
            in your environment.
          </p>
        )}

        <ModelField
          hint={selected ? `Env default: ${selected.default_model}` : undefined}
          value={model}
          onChange={onModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-gen-models"
          ollama={ollama}
        />

        {selected && !selected.configured && (
          <p className="text-sm text-warning">
            This provider has no credentials configured — generation will fail
            until set in the environment.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-end">
        <Button onClick={onNext} disabled={pending || !model.trim()}>
          {pending ? "Saving…" : "Next"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 2: Embeddings
// ---------------------------------------------------------------------------

function Step2Embeddings({
  config,
  ollama,
  provider,
  model,
  onProvider,
  onModel,
  error,
  pending,
  onBack,
  onNext,
}: {
  config: LLMConfig | undefined;
  ollama: OllamaModels | undefined;
  provider: string;
  model: string;
  onProvider: (p: string) => void;
  onModel: (m: string) => void;
  error: string | null;
  pending: boolean;
  onBack: () => void;
  onNext: () => void;
}) {
  const embedding = config?.embedding;
  const selected = embedding?.providers.find((p) => p.name === provider);

  if (!config || !embedding) return <Skeleton className="h-64 w-full" />;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Embeddings</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Choose the model that converts text into vectors for semantic search.
        </p>
      </div>

      <div className="space-y-4">
        <Field
          label="Provider"
          hint="The vector width is bound to the index; switching width needs a migration + re-embed."
        >
          <Select value={provider} onValueChange={onProvider}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {embedding.providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name} · {p.dimensions} dims
                  {p.applicable ? "" : " — needs migration"}
                  {p.configured ? "" : " — not configured"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <ModelField
          hint={selected ? `Default: ${selected.default_model}` : undefined}
          value={model}
          onChange={onModel}
          placeholder={selected?.default_model}
          isOllama={provider === "ollama"}
          listId="ollama-embed-models"
          ollama={ollama}
        />

        {selected && !selected.applicable && (
          <p className="text-sm text-warning">
            {selected.dimensions} dims ≠ current {embedding.dimensions}. Set
            WPRAG_EMBEDDING_PROVIDER, run migrations, and re-ingest to switch
            width.
          </p>
        )}

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onBack}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button onClick={onNext} disabled={pending || !model.trim()}>
          {pending ? "Saving…" : "Next"}
          {!pending && <i className="ti ti-arrow-right ml-1.5 text-sm" />}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 3: First plugin
// ---------------------------------------------------------------------------

function Step3Plugin({
  slug,
  name,
  wporgSlug,
  githubRepo,
  types,
  onSlug,
  onName,
  onWporgSlug,
  onGithubRepo,
  onToggleType,
  error,
  phase,
  onBack,
  onFinish,
}: {
  slug: string;
  name: string;
  wporgSlug: string;
  githubRepo: string;
  types: string[];
  onSlug: (v: string) => void;
  onName: (v: string) => void;
  onWporgSlug: (v: string) => void;
  onGithubRepo: (v: string) => void;
  onToggleType: (t: string) => void;
  error: string | null;
  phase: "idle" | "registering" | "completing";
  onBack: () => void;
  onFinish: (e: React.FormEvent) => void;
}) {
  const pending = phase !== "idle";

  return (
    <form onSubmit={onFinish} className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">First plugin</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Register a plugin and choose which documentation sources to ingest.
        </p>
      </div>

      <div className="space-y-4">
        <Field label="Slug" hint="URL-safe identifier, e.g. my-plugin">
          <Input
            value={slug}
            onChange={(e) => onSlug(e.target.value)}
            placeholder="my-plugin"
            required
          />
        </Field>
        <Field label="Name">
          <Input
            value={name}
            onChange={(e) => onName(e.target.value)}
            placeholder="My Plugin"
            required
          />
        </Field>
        <Field label="WordPress.org slug" hint="Optional — enables wp.org sources.">
          <Input
            value={wporgSlug}
            onChange={(e) => onWporgSlug(e.target.value)}
            placeholder="my-plugin"
          />
        </Field>
        <Field label="GitHub repo" hint="Optional — owner/name format.">
          <Input
            value={githubRepo}
            onChange={(e) => onGithubRepo(e.target.value)}
            placeholder="acme/my-plugin"
          />
        </Field>

        <div>
          <Label className="mb-2 block text-sm font-medium">Sources</Label>
          <div className="grid grid-cols-2 gap-2">
            {SOURCE_TYPES.map((type) => (
              <label
                key={type}
                className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-primary"
                  checked={types.includes(type)}
                  onChange={() => onToggleType(type)}
                />
                <span className="font-mono text-[13px]">{type}</span>
              </label>
            ))}
          </div>
        </div>

        {error && <InlineError message={error} />}
      </div>

      <div className="flex justify-between">
        <Button type="button" variant="ghost" onClick={onBack} disabled={pending}>
          <i className="ti ti-arrow-left mr-1.5 text-sm" /> Back
        </Button>
        <Button
          type="submit"
          disabled={pending || !slug.trim() || !name.trim()}
        >
          {phase === "registering"
            ? "Registering…"
            : phase === "completing"
              ? "Finishing…"
              : "Finish"}
          {!pending && <i className="ti ti-check ml-1.5 text-sm" />}
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// SetupWizardPage
// ---------------------------------------------------------------------------

export function SetupWizardPage() {
  const [step, setStep] = useState<Step>(1);

  // Step 1
  const [genProvider, setGenProvider] = useState("");
  const [genModel, setGenModel] = useState("");

  // Step 2
  const [embedProvider, setEmbedProvider] = useState("");
  const [embedModel, setEmbedModel] = useState("");

  // Step 3
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [wporgSlug, setWporgSlug] = useState("");
  const [githubRepo, setGithubRepo] = useState("");
  const [types, setTypes] = useState<string[]>(["wporg_faq", "wporg_changelog"]);

  const [error, setError] = useState<string | null>(null);
  const [step3Phase, setStep3Phase] = useState<"idle" | "registering" | "completing">("idle");

  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["llm-config"], queryFn: getLlmConfig });
  const ollama = useQuery({ queryKey: ["ollama-models"], queryFn: getOllamaModels });

  useEffect(() => {
    if (!config.data) return;
    if (!genProvider) {
      setGenProvider(config.data.provider);
      setGenModel(config.data.model);
    }
    if (!embedProvider && config.data.embedding) {
      setEmbedProvider(config.data.embedding.provider);
      setEmbedModel(config.data.embedding.model);
    }
  }, [config.data, genProvider, embedProvider]);

  const saveGen = useMutation({
    mutationFn: () =>
      updateLlmConfig({ provider: genProvider, model: genModel.trim() || null }),
    onSuccess: () => {
      setError(null);
      setStep(2);
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  const saveEmbed = useMutation({
    mutationFn: () =>
      updateEmbeddingConfig({
        provider: embedProvider,
        model: embedModel.trim() || null,
      }),
    onSuccess: () => {
      ingestAll().catch(() => undefined);
      setError(null);
      setStep(3);
    },
    onError: (e) => setError(extractErrorMessage(e)),
  });

  function toggleType(type: string) {
    setTypes((cur) =>
      cur.includes(type) ? cur.filter((t) => t !== type) : [...cur, type],
    );
  }

  async function handleFinish(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setStep3Phase("registering");
      await registerPlugin({
        slug: slug.trim(),
        name: name.trim(),
        wporg_slug: wporgSlug.trim() || null,
        github_repo: githubRepo.trim() || null,
        source_types: types,
      });
      ingestPlugin(slug.trim()).catch(() => undefined);
      setStep3Phase("completing");
      await completeSetup();
      await queryClient.invalidateQueries({ queryKey: ["setup-status"] });
      navigate("/", { replace: true, state: { setupComplete: true } });
    } catch (err) {
      setError(extractErrorMessage(err));
      setStep3Phase("idle");
    }
  }

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: "var(--background)" }}>
      <LeftPanel step={step} />
      <div className="flex flex-1 items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-[440px] space-y-8">
          <Stepper current={step} />
          {step === 1 && (
            <Step1Generation
              config={config.data}
              ollama={ollama.data}
              provider={genProvider}
              model={genModel}
              onProvider={(p) => {
                setGenProvider(p);
                const info = config.data?.providers.find((x) => x.name === p);
                if (info) setGenModel(info.default_model);
              }}
              onModel={setGenModel}
              error={error}
              pending={saveGen.isPending}
              onNext={() => {
                setError(null);
                saveGen.mutate();
              }}
            />
          )}
          {step === 2 && (
            <Step2Embeddings
              config={config.data}
              ollama={ollama.data}
              provider={embedProvider}
              model={embedModel}
              onProvider={(p) => {
                setEmbedProvider(p);
                const info = config.data?.embedding?.providers.find(
                  (x) => x.name === p,
                );
                if (info) setEmbedModel(info.default_model);
              }}
              onModel={setEmbedModel}
              error={error}
              pending={saveEmbed.isPending}
              onBack={() => {
                setError(null);
                setStep(1);
              }}
              onNext={() => {
                setError(null);
                saveEmbed.mutate();
              }}
            />
          )}
          {step === 3 && (
            <Step3Plugin
              slug={slug}
              name={name}
              wporgSlug={wporgSlug}
              githubRepo={githubRepo}
              types={types}
              onSlug={setSlug}
              onName={setName}
              onWporgSlug={setWporgSlug}
              onGithubRepo={setGithubRepo}
              onToggleType={toggleType}
              error={error}
              phase={step3Phase}
              onBack={() => {
                setError(null);
                setStep(2);
              }}
              onFinish={handleFinish}
            />
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
pnpm --filter @wp-support-rag/admin type-check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/admin/src/pages/SetupWizardPage.tsx
git commit -m "feat(admin): SetupWizardPage — 3-step generation/embeddings/plugin wizard"
```

---

## Task 7: Frontend — route + Dashboard banner

**Files:**
- Modify: `apps/admin/src/app/routes.tsx`
- Modify: `apps/admin/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Add `/setup` route to `apps/admin/src/app/routes.tsx`**

Add import at top (with existing page imports):
```typescript
import { SetupWizardPage } from "@/pages/SetupWizardPage";
```

Add the route as a sibling to the `ProtectedShell` route, inside `Root`'s children array, **before** the `ProtectedShell` entry (`path: "/"`):

```typescript
{ path: "/setup", element: <RequireAuth><SetupWizardPage /></RequireAuth> },
```

The `RequireAuth` import is already available (used by `ProtectedShell`). Add it to the import from `@/lib/auth`:

```typescript
import { AuthProvider, RequireAuth } from "@/lib/auth";
```

Full children array after change:
```typescript
children: [
  { path: "/login", element: <LoginPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  { path: "/accept-invite", element: <AcceptInvitePage /> },
  { path: "/setup", element: <RequireAuth><SetupWizardPage /></RequireAuth> },
  {
    path: "/",
    element: <ProtectedShell />,
    children: [ ... ],
  },
],
```

- [ ] **Step 2: Add `SetupCompleteBanner` to `apps/admin/src/pages/DashboardPage.tsx`**

Add imports at the top of DashboardPage.tsx (alongside existing imports):
```typescript
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
```

Add the `SetupCompleteBanner` component before `DashboardPage`:

```typescript
function SetupCompleteBanner() {
  const location = useLocation();
  const navigate = useNavigate();
  const [visible, setVisible] = useState(
    () =>
      location.state?.setupComplete === true &&
      localStorage.getItem("setup-banner-dismissed") !== "true",
  );

  useEffect(() => {
    if (location.state?.setupComplete) {
      navigate(".", { replace: true, state: {} });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!visible) return null;

  return (
    <div className="flex items-start gap-3 rounded-lg border border-primary/20 bg-accent px-4 py-3 text-sm">
      <i className="ti ti-circle-check text-primary text-base shrink-0 mt-0.5" />
      <div className="flex-1">
        <span className="font-medium text-foreground">Setup complete</span>
        <span className="text-muted-foreground ml-1">
          — generation, embeddings, and your first plugin are configured.
          Ingestion is running in the background.
        </span>
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => {
          localStorage.setItem("setup-banner-dismissed", "true");
          setVisible(false);
        }}
        className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
      >
        <i className="ti ti-x text-sm" />
      </button>
    </div>
  );
}
```

Inside `DashboardPage`, render `<SetupCompleteBanner />` as the first child of the outer `<div className="space-y-5">`:

```typescript
return (
  <div className="space-y-5">
    <SetupCompleteBanner />
    <PageHeader ... />
    ...
  </div>
);
```

- [ ] **Step 3: TypeScript check**

```bash
pnpm --filter @wp-support-rag/admin type-check
```

Expected: no errors.

- [ ] **Step 4: Build check**

```bash
pnpm --filter @wp-support-rag/admin build
```

Expected: build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/admin/src/app/routes.tsx apps/admin/src/pages/DashboardPage.tsx
git commit -m "feat(admin): wire /setup route and dashboard setup-complete banner"
```

---

## Self-review checklist

- [x] **Spec coverage:** migration ✓, GET /setup/status ✓, POST /setup/complete ✓, RequireAuth guard ✓, wizard 3 steps ✓, back navigation ✓, fire-and-forget ingestAll/ingestPlugin ✓, completeSetup + invalidate ✓, dashboard banner ✓, dismiss to localStorage ✓, clear router state on mount ✓, fail open on getSetupStatus error ✓, hard gate (no skip) ✓
- [x] **No placeholders:** all code complete
- [x] **Type consistency:** `SetupStatus` interface defined in Task 4 step 1; used in `getSetupStatus`/`completeSetup` return types and `RequireAuth` query; `SetupStatusResponse` schema in Task 2 step 1 mirrors it. `SystemSetting` model in Task 1 step 1 is imported in `routes_setup.py` Task 2 step 3. `require_any_admin` added in Task 2 step 2 and imported in `routes_setup.py` Task 2 step 3.

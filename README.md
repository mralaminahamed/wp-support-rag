# WP Plugin Support Desk RAG

[![CI](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/ci.yml)
[![Frontend](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/frontend.yml/badge.svg)](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/frontend.yml)

**Author:** Al Amin Ahamed ([@mralaminahamed](https://github.com/mralaminahamed))

A self-hosted Retrieval-Augmented Generation service that answers WordPress
plugin support questions from a grounded corpus of the author's own documentation
(GitHub READMEs/CHANGELOGs/docs/issues and WordPress.org FAQ/changelog/support
threads). It deflects repetitive support tickets with instant, **cited** answers,
and fails open to retrieved links when the LLM is unavailable.

## How it works

```
widget → POST /api/v1/query
  → route (plugin slug or centroid routing)
  → hybrid retrieve (HNSW cosine + Postgres FTS, merged by RRF)
  → generate (cache → cost breaker → provider → citation validation → cache)
  → cited answer  (or degraded links / decline)
```

- **Frameworkless** pgvector RAG — no LangChain/LlamaIndex in the hot path.
- **Embeddings**: OpenAI `text-embedding-3-large` as `halfvec(3072)` with an HNSW
  index, or **fully-local Ollama** (e.g. `nomic-embed-text`, 768-dim) — selected by
  config. The vector width is bound to the column + index, so switching providers
  needs a migration and a re-embed (not a runtime toggle).
- **Hybrid retrieval**: vector + lexical fused with Reciprocal Rank Fusion.
- **Multi-provider generation**: Claude, OpenAI, or Ollama, interchangeable by config
  and switchable at runtime from the admin Settings page.
- **Runs fully local**: point generation *and* embeddings at Ollama and the whole
  pipeline needs no external API.
- **Grounded & cited**: only source URLs of supplied chunks may be cited.
- **Resilient**: fail-open on provider outage (degraded links); a clear 503 when the
  embeddings provider is unconfigured; per-request cost circuit breaker.

See `docs/` for the full SRS, architecture, implementation plan, and ADRs.

## Repository layout

A monorepo: a pnpm + Turborepo workspace for the JS apps, with the Python service
self-contained under `apps/api`.

```
apps/
  api/    # Python backend — FastAPI + Celery (package `app`, eval/, tests/, scripts/, own pyproject + uv.lock)
    app/seeders/   # Laravel-style dev seeders (roles, users, plugins)
    app/cli.py     # CLI entry point (seed command)
    scripts/       # one-off scripts: sync_plugins, seed_dev
  web/    # embeddable support widget (single-file, no build)
  admin/  # admin console — Vite + React + TypeScript
config/plugins/   # declarative plugin registrations (FR-PM-5; see config/README.md)
docker-compose*.yml  pnpm-workspace.yaml  turbo.json
```

Python commands run from `apps/api`; JS commands (`pnpm dev/build`) from the root.

## Quickstart (local)

```bash
cd apps/api && uv sync                    # install (Python lives here)
docker compose up -d                      # postgres+pgvector, redis, app, worker, beat
cd apps/api && uv run alembic upgrade head
curl localhost:8000/health                # {"status":"ok",...}

# Optional: seed dev accounts + sample plugins
uv run python -m app.cli                  # roles, users, plugins (idempotent)
```

`docker compose up` runs all services: **api** (`:8000`), worker, beat, Postgres,
Redis, the **widget** (`web`, `:8080`), and the **admin** console (`admin`, `:8081`).
In production (`docker-compose.prod.yml`) Caddy serves the API + widget on
`$DOMAIN` and the admin console on `admin.$DOMAIN`, all with automatic TLS.

Set provider keys / selection in `.env` (see `.env.example`):

```
WPRAG_OPENAI_API_KEY=...        # embeddings (OpenAI mode) + OpenAI generation
WPRAG_ANTHROPIC_API_KEY=...     # Claude provider
WPRAG_DEFAULT_PROVIDER=ollama   # generation provider: anthropic | openai | ollama
WPRAG_EMBEDDING_PROVIDER=ollama # embeddings backend: openai (default) | ollama
WPRAG_OLLAMA_BASE_URL=http://host.docker.internal:11434  # reach a host Ollama from Docker
WPRAG_GITHUB_TOKEN=...          # raises the GitHub rate limit + enables private-repo ingestion
WPRAG_JWT_SECRET=...            # HS256 signing key — generate with: openssl rand -hex 32
WPRAG_BOOTSTRAP_EMAIL=admin@example.com   # first super_admin account (seeded on first boot)
WPRAG_BOOTSTRAP_PASSWORD=...             # password for the bootstrap account
```

For a fully-local setup, run [Ollama](https://ollama.com) on the host
(`ollama pull llama3.2 && ollama pull nomic-embed-text`), keep the defaults above,
then `alembic upgrade head` and re-ingest so the embedding column matches the
local model's width. No OpenAI/Anthropic key is then required.

**Admin authentication** uses HTTP-only cookie JWT sessions (no bearer tokens).
On first boot, when the users table is empty, the service seeds a `super_admin`
account using `WPRAG_BOOTSTRAP_EMAIL` / `WPRAG_BOOTSTRAP_PASSWORD`. Log in at
`http://localhost:8081/login`. All subsequent admin accounts are created from the
Users page or via invite links.

## Embed the widget

One script tag on any external page (no build step):

```html
<script src="https://your-host/widget.js"
        data-plugin-slug="swift-menu-duplicator"
        data-api-base="https://your-api-host"></script>
```

It posts to `/api/v1/query`, renders the cited answer, and offers a
helpful/not-helpful control posting to `/api/v1/feedback`. See `apps/web/index.html`
for a working external-page demo.

## Admin console

The `admin` app (`:8081`, `apps/admin`) is a React console for operating the service:

- **Login** — email + password form; sessions use HTTP-only cookies (no localStorage).
- **Dashboard** — service health, query metrics, corpus coverage, and a recent-activity feed.
- **Plugins** — searchable/sortable registry; expand a plugin to see its sources and trigger ingestion.
- **Playground** — a chat-style interface for grounded, cited Q&A (each turn is an independent RAG query, streamed).
- **Users** — create accounts, send invite links (48 h TTL), manage roles and per-user permission overrides. Visible to users with `users:read`.
- **Settings** — switch the generation and embedding provider/model at runtime (with an Ollama model picker), test the API connection, and set your profile (name + email → Gravatar avatar). Light/dark theme.

## API

**Auth** uses HTTP-only cookie JWT sessions. The `access_token` cookie (15 min TTL)
carries a signed JWT with the user's effective permission set embedded. A
`refresh_token` cookie (7 day TTL, scoped to `/api/v1/auth/refresh`) silently
reissues the access token. No `Authorization` header is needed.

**Permissions** are fine-grained strings: `plugins:read`, `plugins:write`,
`ingestion:trigger`, `metrics:read`, `settings:read`, `settings:write`,
`users:read`, `users:write`, `users:invite`. System roles (`super_admin`, `admin`,
`viewer`) bundle these; per-user overrides add or remove individual permissions.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness + DB/Redis probes |
| POST | `/api/v1/query` | per-IP rate limit | Ask a question; returns a cited answer + `query_id` |
| POST | `/api/v1/query/stream` | per-IP rate limit | Same, streamed as SSE: `token` events then a `done` event |
| POST | `/api/v1/feedback` | per-IP rate limit | Bind `helpful`/`not_helpful` to a `query_id` |
| POST | `/api/v1/auth/login` | — | Email + password → sets `access_token` + `refresh_token` cookies |
| POST | `/api/v1/auth/refresh` | refresh cookie | Reissue access token |
| POST | `/api/v1/auth/logout` | — | Clear auth cookies |
| GET | `/api/v1/auth/me` | cookie | Current user info + effective permissions |
| POST | `/api/v1/auth/register` | — (if `WPRAG_ALLOW_REGISTRATION=true`) | Self-registration |
| POST | `/api/v1/auth/accept-invite` | — | Accept an invite token and set password |
| GET·POST | `/api/v1/admin/users` | `users:read` / `users:write` | List / create users |
| GET·PATCH·DELETE | `/api/v1/admin/users/{id}` | `users:read` / `users:write` | Get / update / delete a user |
| POST | `/api/v1/admin/users/{id}/invite` | `users:invite` | Send an invite link (48 h TTL) |
| GET·POST | `/api/v1/admin/roles` | `users:read` / `users:write` | List / create roles |
| GET·PATCH·DELETE | `/api/v1/admin/roles/{id}` | `users:read` / `users:write` | Get / update / delete a role |
| POST | `/api/v1/admin/plugins` | `plugins:write` | Register a plugin and its sources |
| GET | `/api/v1/admin/plugins` | `plugins:read` | List registered plugins with source counts |
| GET | `/api/v1/admin/plugins/{slug}/sources` | `plugins:read` | List a plugin's sources and ingestion state |
| POST | `/api/v1/admin/ingest` | `ingestion:trigger` | Trigger ingestion for every plugin's sources |
| POST | `/api/v1/admin/ingest/{slug}` | `ingestion:trigger` | Trigger ingestion (one Celery task per source) |
| GET | `/api/v1/admin/metrics` | `metrics:read` | Deflection, helpful, cache-hit, degraded rates, mean cost, p95 latency (optional `?plugin_slug=`) |
| GET | `/api/v1/admin/queries` | `metrics:read` | Recent queries for the activity feed (`?limit=`) |
| GET·PUT·DELETE | `/api/v1/admin/llm` | `settings:read` / `settings:write` | Read / override / reset the active generation provider+model |
| PUT·DELETE | `/api/v1/admin/llm/embedding` | `settings:write` | Override / reset the embedding provider+model (same vector width only) |
| GET | `/api/v1/admin/ollama/models` | `settings:read` | List models available on the configured Ollama server |

The widget streams from `/api/v1/query/stream` where available and falls back to
`/api/v1/query`. Streamed tokens are provisional; the closing `done` event carries
the citation-validated answer.

## Production deployment

```bash
DOMAIN=support.example.com POSTGRES_PASSWORD=… \
WPRAG_JWT_SECRET=$(openssl rand -hex 32) \
WPRAG_BOOTSTRAP_EMAIL=admin@example.com WPRAG_BOOTSTRAP_PASSWORD=… \
WPRAG_OPENAI_API_KEY=… WPRAG_ANTHROPIC_API_KEY=… \
docker compose -f docker-compose.prod.yml up -d
```

Caddy terminates TLS automatically for `$DOMAIN` and reverse-proxies the API.
All secrets are environment-only. See `RUNBOOK.md` for day-two operations.

## Quality gates

```bash
# Backend (from apps/api)
ruff check . && ruff format --check .       # lint + format
mypy --strict app eval                      # types
pytest                                       # tests (external calls mocked/VCR-replayed)
python -m eval.harness                       # offline eval gate

# Admin console (from repo root)
pnpm --filter @wp-support-rag/admin type-check
pnpm --filter @wp-support-rag/admin lint
pnpm --filter @wp-support-rag/admin build
pnpm --filter @wp-support-rag/admin e2e      # Playwright (API mocked)
```

CI runs backend lint/typecheck/test and the admin build + e2e on every push; the
eval gate runs on changes under `apps/api/app/prompts/`, `apps/api/app/rag/`, or
`apps/api/eval/dataset/` and blocks regressions.

> Note: the embedding dimension is bound to the DB column + HNSW index, so the
> backend integration tests must run against a database at the configured width.
> See `RUNBOOK.md` §5 for running tests against a local Ollama (768-dim) dev DB.

## Plugin registry

Plugins are declared in `config/plugins/*.yaml` and synced into the database:

```bash
cd apps/api
WPRAG_DATABASE_DSN=postgresql+asyncpg://wprag:wprag@localhost:5432/wprag \
  python -m scripts.sync_plugins          # add/update; --prune drops undeclared plugins
```

See `config/README.md` for the file schema and source types.

## Development data

Laravel-style seeders populate a fresh database with realistic dev fixtures.
All seeders are idempotent — safe to re-run; use `--fresh` to wipe and re-seed.

```bash
cd apps/api

uv run python -m app.cli                  # seed everything
uv run python -m app.cli --table users    # seed only users
uv run python -m app.cli --table plugins  # seed only plugins
uv run python -m app.cli --fresh          # truncate seeded rows then re-seed
```

**Seeded roles**

| Role | Permissions |
|------|-------------|
| `super_admin` *(system)* | all 9 |
| `admin` *(system)* | all except `users:*` |
| `viewer` *(system)* | `plugins:read`, `metrics:read` |
| `editor` *(custom)* | `plugins:read/write`, `ingestion:trigger` |

**Seeded accounts** (password `DevPass123!` — dev only, never use in production)

| Email | Role | Active |
|-------|------|--------|
| `superadmin@dev.local` | super_admin | yes |
| `admin@dev.local` | admin | yes |
| `editor@dev.local` | editor | yes |
| `viewer@dev.local` | viewer | yes |
| `inactive@dev.local` | viewer | **no** |

**Seeded plugins**

| Slug | Sources |
|------|---------|
| `hello-dolly` | wporg_faq, wporg_changelog |
| `woocommerce` | wporg_faq, wporg_changelog, github_readme |
| `contact-form-7` | wporg_faq, wporg_changelog, wporg_support |

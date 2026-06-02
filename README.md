# WP Plugin Support Desk RAG

[![CI](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/ci.yml)
[![Frontend](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/frontend.yml/badge.svg)](https://github.com/mralaminahamed/wp-support-rag/actions/workflows/frontend.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Node 24](https://img.shields.io/badge/node-24-339933?logo=node.js&logoColor=white)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![License: MIT](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)

**Self-hosted RAG service that answers WordPress plugin support questions from the author's own documentation — cited, grounded, and fails open to source links when the LLM is unavailable.**

Ingests GitHub READMEs, CHANGELOGs, docs, issues and WordPress.org FAQ, changelog, and support threads. Deflects repetitive support tickets with instant cited answers without hallucinating URLs or undocumented behaviour.

---

## How it works

```
widget → POST /api/v1/query
  → route (plugin slug or centroid routing)
  → hybrid retrieve (HNSW cosine + Postgres FTS, merged by RRF)
  → generate (cache → cost breaker → provider → citation validation → cache)
  → cited answer  (or degraded links / decline)
```

- **Frameworkless** pgvector RAG — no LangChain or LlamaIndex in the hot path.
- **Hybrid retrieval:** vector + lexical fused with Reciprocal Rank Fusion.
- **Multi-provider generation:** Claude, OpenAI, or Ollama — interchangeable by config and switchable at runtime from the admin console.
- **Runs fully local:** point generation *and* embeddings at Ollama; no external API needed.
- **Grounded and cited:** only URLs of retrieved chunks may appear in citations.
- **Resilient:** fail-open on provider outage (degraded links); a clear 503 when the embeddings provider is unconfigured; per-request cost circuit breaker.

---

## Tech stack

| Layer | Technology |
|---|---|
| API | Python 3.12 · FastAPI 0.115 · SQLAlchemy 2.0 async · Alembic · Pydantic v2 |
| Workers | Celery 5 · Redis · httpx async |
| Database | PostgreSQL 16 · pgvector · HNSW cosine · `halfvec(3072)` or `halfvec(768)` |
| Embeddings | OpenAI `text-embedding-3-large` (3072d) · Ollama `nomic-embed-text` (768d, local fallback) |
| LLM | Claude `claude-sonnet-4-6` · OpenAI `gpt-4o-mini` · Ollama `llama3.2` |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · TanStack Query 5 |
| Auth | HTTP-only cookie JWT · fine-grained permissions · role + per-user overrides |
| Infra | Docker Compose · GitHub Actions CI/Deploy · Caddy (prod TLS) |

---

## Prerequisites

- Docker + Docker Compose
- Python 3.12+ with [uv](https://docs.astral.sh/uv/) (`pip install uv`)
- Node.js 24+ with [pnpm](https://pnpm.io/) (`npm i -g pnpm`)

**For local-only dev (no cloud keys needed):**
- [Ollama](https://ollama.com) running on the host with `llama3.2` and `nomic-embed-text` pulled

**Optional cloud providers:**
- `WPRAG_ANTHROPIC_API_KEY` — Claude generation
- `WPRAG_OPENAI_API_KEY` — OpenAI generation + embeddings

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/mralaminahamed/wp-support-rag.git
cd wp-support-rag

# 2. Create .env (gitignored)
cat > .env << 'EOF'
WPRAG_DEFAULT_PROVIDER=ollama
WPRAG_EMBEDDING_PROVIDER=ollama
WPRAG_OLLAMA_BASE_URL=http://host.docker.internal:11434
WPRAG_JWT_SECRET=$(openssl rand -hex 32)
WPRAG_BOOTSTRAP_EMAIL=admin@example.com
WPRAG_BOOTSTRAP_PASSWORD=changeme
EOF

# 3. Pull Ollama models (host, not container)
ollama pull llama3.2
ollama pull nomic-embed-text

# 4. Start the stack
docker compose up -d

# 5. Run migrations
docker compose exec app alembic upgrade head

# 6. Seed dev fixtures (optional)
docker compose exec app python -m app.cli

# 7. Open the admin console
open http://localhost:8081
```

**Services:**

| Service | URL | Notes |
|---|---|---|
| API | http://localhost:8000 | Swagger UI at `/docs` |
| Admin console | http://localhost:8081 | Dashboard, Plugins, Playground, Users, Settings |
| Widget demo | http://localhost:8080 | Embeddable support widget preview |
| PostgreSQL | `localhost:5432` | pgvector database (`db: wprag`, `user: wprag`) |
| Redis | `localhost:6380` | Celery broker + response cache |

**Key environment variables:**

```bash
# Generation provider
WPRAG_DEFAULT_PROVIDER=ollama           # anthropic | openai | ollama
WPRAG_ANTHROPIC_API_KEY=sk-ant-...
WPRAG_OPENAI_API_KEY=sk-...
WPRAG_OLLAMA_BASE_URL=http://host.docker.internal:11434

# Embeddings
WPRAG_EMBEDDING_PROVIDER=ollama         # openai (default) | ollama
WPRAG_OLLAMA_EMBED_MODEL=nomic-embed-text

# Auth (required)
WPRAG_JWT_SECRET=...                    # generate: openssl rand -hex 32
WPRAG_BOOTSTRAP_EMAIL=admin@example.com
WPRAG_BOOTSTRAP_PASSWORD=...

# Optional
WPRAG_GITHUB_TOKEN=...                  # raises GitHub rate limit + private repos
WPRAG_ALLOW_REGISTRATION=false          # open self-registration
WPRAG_ADMIN_URL=http://localhost:8081   # base URL for invite links
```

---

## Embed the widget

One script tag on any external page (no build step):

```html
<script src="https://your-host/widget.js"
        data-plugin-slug="your-plugin-slug"
        data-api-base="https://your-api-host"></script>
```

Posts to `/api/v1/query`, renders the cited answer, and collects helpful/not-helpful feedback. See `apps/web/index.html` for a working demo.

---

## Admin console pages

| Page | Route | Description |
|---|---|---|
| Dashboard | `/` | Service health, query metrics, corpus coverage, recent activity |
| Plugins | `/plugins` | Searchable registry; expand a plugin to see sources and trigger ingestion |
| Playground | `/playground` | Chat-style grounded Q&A with source attribution (streamed) |
| Users | `/users` | Create accounts, send invite links, manage roles and permission overrides |
| Settings | `/settings/generation` | Switch generation provider/model at runtime |
| Settings | `/settings/embeddings` | Switch embedding provider/model (triggers re-ingestion) |
| Profile | `/profile/overview` | Account details and roles |
| Profile | `/profile/security` | Change password, session info |
| Profile | `/profile/permissions` | Effective permission set grouped by namespace |

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Liveness + DB/Redis probes |
| `POST` | `/api/v1/query` | rate-limited | Grounded answer with citations and `query_id` |
| `POST` | `/api/v1/query/stream` | rate-limited | SSE: `token` events then `done` with citation-validated answer |
| `POST` | `/api/v1/feedback` | rate-limited | Bind `helpful`/`not_helpful` to a `query_id` |
| `POST` | `/api/v1/auth/login` | — | Email + password → sets `access_token` + `refresh_token` cookies |
| `POST` | `/api/v1/auth/refresh` | refresh cookie | Reissue access token |
| `POST` | `/api/v1/auth/logout` | — | Clear auth cookies |
| `GET` | `/api/v1/auth/me` | cookie | Current user + effective permissions |
| `POST` | `/api/v1/auth/register` | — (if `ALLOW_REGISTRATION=true`) | Self-registration |
| `POST` | `/api/v1/auth/accept-invite` | — | Accept invite token and set password |
| `GET·POST` | `/api/v1/admin/users` | `users:read/write` | List / create users |
| `GET·PATCH·DELETE` | `/api/v1/admin/users/{id}` | `users:read/write` | Get / update / delete a user |
| `POST` | `/api/v1/admin/users/{id}/invite` | `users:invite` | Send 48h invite link |
| `GET·POST` | `/api/v1/admin/roles` | `users:read/write` | List / create roles |
| `POST` | `/api/v1/admin/plugins` | `plugins:write` | Register a plugin and its sources |
| `GET` | `/api/v1/admin/plugins` | `plugins:read` | List registered plugins with source counts |
| `GET` | `/api/v1/admin/plugins/{slug}/sources` | `plugins:read` | List a plugin's sources and ingestion state |
| `POST` | `/api/v1/admin/ingest` | `ingestion:trigger` | Trigger ingestion for all plugins |
| `POST` | `/api/v1/admin/ingest/{slug}` | `ingestion:trigger` | Trigger ingestion for one plugin |
| `GET` | `/api/v1/admin/metrics` | `metrics:read` | Deflection, cache-hit, p95 latency, mean cost (`?plugin_slug=`) |
| `GET` | `/api/v1/admin/queries` | `metrics:read` | Recent queries for the activity feed (`?limit=`) |
| `GET·PUT·DELETE` | `/api/v1/admin/llm` | `settings:read/write` | Read / override / reset generation provider+model |
| `PUT·DELETE` | `/api/v1/admin/llm/embedding` | `settings:write` | Override / reset embedding provider+model |
| `GET` | `/api/v1/admin/ollama/models` | `settings:read` | List models available on the Ollama server |

Full interactive docs: `http://localhost:8000/docs`

---

## Plugin registry

Plugins are registered via the admin console (Plugins page) or declared in `config/plugins/*.yaml` and synced:

```bash
cd apps/api
WPRAG_DATABASE_DSN=postgresql+asyncpg://wprag:wprag@localhost:5432/wprag \
  python -m scripts.sync_plugins           # add/update
  python -m scripts.sync_plugins --prune   # also drop undeclared plugins
```

See `config/README.md` for the file schema and supported source types (`github_readme`, `github_changelog`, `github_docs`, `github_issues`, `wporg_faq`, `wporg_changelog`, `wporg_support`).

---

## Database migrations

```bash
# Apply all pending (local dev, from apps/api/)
uv run alembic upgrade head

# Create autogenerated migration
uv run alembic revision --autogenerate -m "describe change"

# Rollback one step
uv run alembic downgrade -1
```

---

## Development

```bash
# Backend (from apps/api/)
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app eval
uv run pytest -q                          # all external calls mocked/VCR-replayed
uv run python -m eval.harness             # offline eval gate

# Admin console (from repo root)
pnpm --filter @wp-support-rag/admin type-check
pnpm --filter @wp-support-rag/admin lint
pnpm --filter @wp-support-rag/admin build
pnpm --filter @wp-support-rag/admin e2e   # Playwright (API mocked)
```

**Quality gates (must pass before merge):**

```
ruff check + format --check
mypy --strict app eval
pytest

pnpm type-check && pnpm build

# On changes to app/prompts/, app/rag/, eval/dataset/:
python -m eval.harness
```

---

## Development data

Laravel-style seeders populate a fresh database with realistic dev fixtures. All seeders are idempotent — safe to re-run; use `--fresh` to wipe and re-seed.

```bash
cd apps/api

uv run python -m app.cli                  # seed everything
uv run python -m app.cli --table users    # seed only users
uv run python -m app.cli --table plugins  # seed only plugins
uv run python -m app.cli --fresh          # truncate then re-seed
```

**Seeded roles:**

| Role | Permissions |
|---|---|
| `super_admin` *(system)* | all 9 |
| `admin` *(system)* | all except `users:*` |
| `viewer` *(system)* | `plugins:read`, `metrics:read` |
| `editor` *(custom)* | `plugins:read/write`, `ingestion:trigger` |

**Seeded accounts** (password `DevPass123!` — dev only, never use in production):

| Email | Role | Active |
|---|---|---|
| `superadmin@dev.local` | super_admin | yes |
| `admin@dev.local` | admin | yes |
| `editor@dev.local` | editor | yes |
| `viewer@dev.local` | viewer | yes |
| `inactive@dev.local` | viewer | **no** |

**Seeded plugins:**

| Slug | Sources |
|---|---|
| `hello-dolly` | wporg_faq, wporg_changelog |
| `woocommerce` | wporg_faq, wporg_changelog, github_readme |
| `contact-form-7` | wporg_faq, wporg_changelog, wporg_support |

---

## Production deployment

```bash
export DOMAIN=support.example.com
export POSTGRES_PASSWORD=$(openssl rand -hex 32)
export WPRAG_JWT_SECRET=$(openssl rand -hex 32)
export WPRAG_BOOTSTRAP_EMAIL=admin@example.com
export WPRAG_BOOTSTRAP_PASSWORD=...
export WPRAG_ANTHROPIC_API_KEY=...
export WPRAG_OPENAI_API_KEY=...

docker compose -f docker-compose.prod.yml up -d
```

Caddy provisions and renews TLS automatically. The admin console is served at `https://admin.$DOMAIN`. All secrets are environment-only — none are baked into images.

See [RUNBOOK.md](RUNBOOK.md) for day-two operations: bootstrap, ingestion, prompt rollback, LLM override, and incident response.

---

## Project structure

```
wp-support-rag/
├── apps/
│   ├── api/                    # Python backend
│   │   ├── app/
│   │   │   ├── api/            # FastAPI routes + schemas + deps
│   │   │   ├── db/             # Engine, SQLAlchemy models, Alembic migrations
│   │   │   ├── ingestion/      # GitHub + WP.org crawlers, parsers, Celery tasks
│   │   │   ├── llm/            # Provider protocol (Claude/OpenAI/Ollama), factory, runtime
│   │   │   ├── processing/     # Chunker, embedder (OpenAI + Ollama)
│   │   │   ├── prompts/        # Versioned prompts
│   │   │   ├── rag/            # Retriever, service, citation, generator
│   │   │   ├── seeders/        # Laravel-style dev seeders (roles, users, plugins)
│   │   │   ├── cli.py          # CLI entry point (seed command)
│   │   │   └── config.py       # pydantic-settings; single source of all tunables
│   │   ├── eval/
│   │   │   ├── dataset/        # golden.jsonl — eval dataset
│   │   │   ├── metrics.py      # domain-specific metrics
│   │   │   └── harness.py      # Offline eval harness (python -m eval.harness)
│   │   ├── scripts/            # sync_plugins and other one-off scripts
│   │   └── tests/              # pytest; all external calls mocked or VCR-replayed
│   ├── admin/                  # React 19 + Vite admin console
│   │   └── src/
│   │       ├── pages/          # Dashboard, Plugins, Playground, Users, Settings, Profile
│   │       ├── components/     # Layout (AppShell, AuthLayout) + reusable UI
│   │       ├── api/            # Axios clients (admin + query)
│   │       └── types/          # Shared TypeScript interfaces
│   └── web/                    # Embeddable support widget (single-file, no build)
├── caddy/Caddyfile             # Reverse proxy + TLS config
├── config/
│   └── plugins/                # Declarative plugin YAML registrations
├── docs/
│   ├── 01-SRS.md
│   ├── 02-Architecture.md
│   └── superpowers/            # Specs and implementation plans
├── .github/
│   └── workflows/              # ci.yml · frontend.yml · deploy.yml
├── RUNBOOK.md                  # Day-two operations
├── docker-compose.yml          # Dev stack
└── docker-compose.prod.yml     # Prod stack (Caddy auto-TLS)
```

---

## What is genuinely different

If you have built a general-purpose RAG before, three things work differently here:

1. **Citation URLs come from the corpus, not the model** — `app/rag/citation.py` resolves citations against the retrieved chunk set. Any URL the model tries to emit that was not in the supplied chunks is stripped. The model cannot hallucinate a support forum link that doesn't exist in your indexed sources.

2. **Routing is centroid-based, not keyword-based** — when a query does not target a specific plugin slug, `app/rag/retriever.py` embeds the question and ranks plugins by centroid similarity before retrieval. A question about "duplicating nav menus" routes to the correct plugin without the user specifying a slug. Plugin centroids are cached in Redis with a 7-day TTL.

3. **The embedding dimension is bound to the DB column and HNSW index** — switching from OpenAI (3072d) to Ollama (768d) or back requires a migration and a full re-embed, not a config toggle. The admin console shows a warning when you select a provider with a different dimension. See the Embeddings settings tab for the current active width.

---

## Auth

**Admin authentication** uses HTTP-only cookie JWT sessions — no bearer tokens, no localStorage.

The `access_token` cookie (15 min TTL) carries a signed JWT with the user's effective permission set. A `refresh_token` cookie (7 day TTL, scoped to `/api/v1/auth/refresh`) silently reissues the access token.

**Permissions** are fine-grained strings: `plugins:read`, `plugins:write`, `ingestion:trigger`, `metrics:read`, `settings:read`, `settings:write`, `users:read`, `users:write`, `users:invite`. System roles (`super_admin`, `admin`, `viewer`) bundle these; per-user overrides add or remove individual permissions.

On first boot the service seeds a `super_admin` account using `WPRAG_BOOTSTRAP_EMAIL` / `WPRAG_BOOTSTRAP_PASSWORD`. All subsequent accounts are created from the Users page or via invite links.

---

## License

MIT © 2026 [Al Amin Ahamed](https://github.com/mralaminahamed)

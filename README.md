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
WPRAG_ADMIN_BEARER_TOKEN=...    # admin endpoints
```

For a fully-local setup, run [Ollama](https://ollama.com) on the host
(`ollama pull llama3.2 && ollama pull nomic-embed-text`), keep the defaults above,
then `alembic upgrade head` and re-ingest so the embedding column matches the
local model's width. No OpenAI/Anthropic key is then required.

The admin token is an opaque, high-entropy secret you generate (no fixed format);
the API compares the `Authorization` header to `Bearer <token>` exactly:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # or: openssl rand -base64 32
```

Keep it out of version control (`.env` is git-ignored) and supply it via the
environment in production. Without it, every `/api/v1/admin/*` endpoint returns 401.

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

- **Dashboard** — service health, query metrics, corpus coverage, and a recent-activity feed.
- **Plugins** — searchable/sortable registry; expand a plugin to see its sources and trigger ingestion.
- **Playground** — a chat-style interface for grounded, cited Q&A (each turn is an independent RAG query, streamed).
- **Settings** — switch the generation and embedding provider/model at runtime (with an Ollama model picker), test the API connection, and set your profile (name + email → Gravatar avatar). Light/dark theme.

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness + DB/Redis probes |
| POST | `/api/v1/query` | per-IP rate limit | Ask a question; returns a cited answer + `query_id` |
| POST | `/api/v1/query/stream` | per-IP rate limit | Same, streamed as SSE: `token` events then a `done` event |
| POST | `/api/v1/feedback` | per-IP rate limit | Bind `helpful`/`not_helpful` to a `query_id` |
| POST | `/api/v1/admin/plugins` | bearer | Register a plugin and its sources |
| GET | `/api/v1/admin/plugins` | bearer | List registered plugins with source counts |
| GET | `/api/v1/admin/plugins/{slug}/sources` | bearer | List a plugin's sources and ingestion state |
| POST | `/api/v1/admin/ingest` | bearer | Trigger ingestion for every plugin's sources |
| POST | `/api/v1/admin/ingest/{slug}` | bearer | Trigger ingestion (one Celery task per source) |
| GET | `/api/v1/admin/metrics` | bearer | Deflection, helpful, cache-hit, degraded rates, mean cost, p95 latency (optional `?plugin_slug=`) |
| GET | `/api/v1/admin/queries` | bearer | Recent queries for the activity feed (`?limit=`) |
| GET·PUT·DELETE | `/api/v1/admin/llm` | bearer | Read / override / reset the active generation provider+model |
| PUT·DELETE | `/api/v1/admin/llm/embedding` | bearer | Override / reset the embedding provider+model (same vector width only) |
| GET | `/api/v1/admin/ollama/models` | bearer | List models available on the configured Ollama server |

The widget streams from `/api/v1/query/stream` where available and falls back to
`/api/v1/query`. Streamed tokens are provisional; the closing `done` event carries
the citation-validated answer.

## Production deployment

```bash
DOMAIN=support.example.com POSTGRES_PASSWORD=… WPRAG_ADMIN_BEARER_TOKEN=… \
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

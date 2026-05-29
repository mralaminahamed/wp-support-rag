# WP Plugin Support Desk RAG

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
- **Embeddings**: `text-embedding-3-large` stored as `halfvec(3072)` with an HNSW
  index (config fallback to `vector(1536)`).
- **Hybrid retrieval**: vector + lexical fused with Reciprocal Rank Fusion.
- **Multi-provider generation**: Claude, OpenAI, or Ollama, interchangeable by config.
- **Grounded & cited**: only source URLs of supplied chunks may be cited.
- **Resilient**: fail-open on provider outage; per-request cost circuit breaker.

See `docs/` for the full SRS, architecture, implementation plan, and ADRs.

## Repository layout

A monorepo: a pnpm + Turborepo workspace for the JS apps, with the Python service
self-contained under `apps/api`.

```
apps/
  api/    # Python backend — FastAPI + Celery (package `app`, eval/, tests/, own pyproject + uv.lock)
  web/    # embeddable support widget (single-file, no build)
  admin/  # admin console — Vite + React + TypeScript
config/plugins/   # declarative plugin registrations (FR-PM-5)
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

Set provider keys (for real generation) in `.env` (see `.env.example`):

```
WPRAG_OPENAI_API_KEY=...        # embeddings + OpenAI provider
WPRAG_ANTHROPIC_API_KEY=...     # Claude provider
WPRAG_ADMIN_BEARER_TOKEN=...    # admin endpoints
```

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
helpful/not-helpful control posting to `/api/v1/feedback`. See `apps/web/index.html` (and an admin console at `apps/web/admin.html`)
for a working external-page demo.

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
| POST | `/api/v1/admin/ingest/{slug}` | bearer | Trigger ingestion (one Celery task per source) |
| GET | `/api/v1/admin/metrics` | bearer | Deflection, helpful, cache-hit, degraded rates, mean cost, p95 latency (optional `?plugin_slug=`) |

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
ruff check . && ruff format --check .     # lint + format
mypy --strict app eval                   # types (from apps/api)
pytest                                    # tests (external calls mocked/VCR-replayed)
python -m eval.harness                     # offline eval gate (from apps/api)
```

CI runs lint/typecheck/test on every push; the eval gate runs on changes under
`apps/api/app/prompts/`, `apps/api/app/rag/`, or `apps/api/eval/dataset/` and blocks regressions.

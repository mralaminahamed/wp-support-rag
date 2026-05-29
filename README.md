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

## Quickstart (local)

```bash
uv sync                                   # install dependencies
docker compose up -d                      # postgres+pgvector, redis, app, worker, beat
uv run alembic upgrade head               # create the schema
curl localhost:8000/health                # {"status":"ok",...}
```

Set provider keys (for real generation) in `.env` (see `.env.example`):

```
WPRAG_OPENAI_API_KEY=...        # embeddings + OpenAI provider
WPRAG_ANTHROPIC_API_KEY=...     # Claude provider
WPRAG_ADMIN_BEARER_TOKEN=...    # admin endpoints
```

## Embed the widget

One script tag on any external page (no build step):

```html
<script src="https://your-host/widget.js"
        data-plugin-slug="swift-menu-duplicator"
        data-api-base="https://your-api-host"></script>
```

It posts to `/api/v1/query`, renders the cited answer, and offers a
helpful/not-helpful control posting to `/api/v1/feedback`. See `widget/index.html`
for a working external-page demo.

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | — | Liveness + DB/Redis probes |
| POST | `/api/v1/query` | per-IP rate limit | Ask a question; returns a cited answer + `query_id` |
| POST | `/api/v1/feedback` | per-IP rate limit | Bind `helpful`/`not_helpful` to a `query_id` |
| POST | `/api/v1/admin/plugins` | bearer | Register a plugin and its sources |
| POST | `/api/v1/admin/ingest/{slug}` | bearer | Trigger ingestion (one Celery task per source) |
| GET | `/api/v1/admin/metrics` | bearer | Deflection, helpful, cache-hit, degraded rates, mean cost, p95 latency |

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
mypy --strict app eval                    # types
pytest                                    # tests (external calls mocked/VCR-replayed)
python -m eval.harness                    # offline eval gate (recall >= 0.85, citation >= 0.95)
```

CI runs lint/typecheck/test on every push; the eval gate runs on changes under
`app/prompts/`, `app/rag/`, or `eval/dataset/` and blocks regressions.

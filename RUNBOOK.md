# Operator Runbook

**Project:** WP Plugin Support Desk RAG · **Author:** Al Amin Ahamed

Day-two operations: register a plugin, ingest its docs, query, and read metrics.
All admin calls use HTTP-only cookie JWT sessions — log in first, then pass
`--cookie-jar` / `--cookie` to carry the session across curl commands.

## 0. Bootstrap the first admin account

On first boot, when the `users` table is empty, the API seeds a `super_admin`
account from `WPRAG_BOOTSTRAP_EMAIL` and `WPRAG_BOOTSTRAP_PASSWORD`. Supply
these in `.env` or the environment before starting the stack (never commit
credentials — `.env` is git-ignored):

```bash
# .env (local) — generate a strong JWT secret once:
WPRAG_JWT_SECRET=$(openssl rand -hex 32)
WPRAG_BOOTSTRAP_EMAIL=admin@example.com
WPRAG_BOOTSTRAP_PASSWORD=<strong-password>
```

Log in at `http://localhost:8081/login` (admin console) or via the API:

```bash
curl -sS -c cookies.txt -X POST "$API/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<password>"}'
# → sets access_token + refresh_token HTTP-only cookies in cookies.txt
```

All subsequent admin API calls pass `-b cookies.txt` to carry the session.
Rotate credentials by updating the password in the Users page; rotate the JWT
secret by changing `WPRAG_JWT_SECRET` and restarting (all sessions expire).

## Session variables

```bash
export API=http://localhost:8000
# Log in once; subsequent calls use -b cookies.txt
curl -sS -c cookies.txt -X POST "$API/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"<password>"}'
```

## 1. Register a plugin

```bash
curl -sS -b cookies.txt -X POST "$API/api/v1/admin/plugins" \
  -H "Content-Type: application/json" \
  -d '{
        "slug": "swift-menu-duplicator",
        "name": "Swift Menu Duplicator",
        "wporg_slug": "swift-menu-duplicator",
        "github_repo": "mralaminahamed/swift-menu-duplicator",
        "source_types": ["github_readme","github_changelog","wporg_faq","wporg_changelog"]
      }'
# → {"slug":"swift-menu-duplicator","id":"<uuid>"}
```

A plugin and its full source set can also be loaded from a declarative file
(`config/plugins/*.yaml`) via `app.ingestion.registry.load_plugin_config`.

List registered plugins:

```bash
curl -sS -b cookies.txt "$API/api/v1/admin/plugins"
# → [{"slug":"swift-menu-duplicator","source_count":4,...}]
```

## 2. Ingest the documentation

```bash
curl -sS -b cookies.txt -X POST "$API/api/v1/admin/ingest/swift-menu-duplicator"
# → {"plugin_slug":"swift-menu-duplicator","enqueued_sources":4}
```

One Celery task runs per `(plugin, source)`; a failing source never aborts the
others. Each fetched document is chunked, embedded, and indexed atomically, and
unchanged documents are skipped by content hash. Watch progress:

```bash
docker compose logs -f worker
```

Re-run anytime — only changed documents are re-embedded. A schedule (Celery beat)
can keep the corpus fresh. Inspect a plugin's sources and last-ingested state:

```bash
curl -sS -b cookies.txt "$API/api/v1/admin/plugins/swift-menu-duplicator/sources"
# → [{"source_type":"wporg_faq","enabled":true,"last_ingested_at":"2026-…"}]
```

## 3. Query

```bash
curl -sS -X POST "$API/api/v1/query" -H "Content-Type: application/json" \
  -d '{"question":"Does duplicating copy theme location assignments?",
       "plugin_slug":"swift-menu-duplicator"}'
```

The response carries the grounded `answer`, `citations` (only supplied source
URLs), `sources` (links for the widget), a `query_id`, and `cached`/`degraded`/
`declined` flags. Omit `plugin_slug` to let centroid routing pick the plugin.

Stream the answer as Server-Sent Events (what the widget uses when available):

```bash
curl -sS -N -X POST "$API/api/v1/query/stream" -H "Content-Type: application/json" \
  -d '{"question":"Does duplicating copy theme location assignments?",
       "plugin_slug":"swift-menu-duplicator"}'
# event: token  → incremental deltas (provisional)
# event: done   → {query_id, answer, citations, sources, ...}  (citation-validated)
```

- **Degraded** (`degraded: true`): every provider was unreachable — the user still
  gets the retrieved passages with links (fail-open).
- **Declined** (`declined: true`): nothing relevant was found — the user is
  directed to open a support request.

Submit feedback against the returned id:

```bash
curl -sS -X POST "$API/api/v1/feedback" -H "Content-Type: application/json" \
  -d '{"query_id":"<uuid>","rating":"helpful"}'
```

## 4. Monitor

```bash
curl -sS -b cookies.txt "$API/api/v1/admin/metrics"
# deflection_rate, helpful_rate, cache_hit_rate, degraded_rate, mean_cost_usd, p95_latency_ms

# Scope to one plugin:
curl -sS -b cookies.txt "$API/api/v1/admin/metrics?plugin_slug=swift-menu-duplicator"
```

Health and dependency reachability:

```bash
curl -sS "$API/health"   # status ok|degraded with per-dependency db/redis state
```

## 5. Running tests against an Ollama dev DB

The embedding **dimension is bound to the `chunks.embedding` column + HNSW
index** (ADR-002). The DB-integration tests embed at `Settings.embedding_dimensions`
and insert into that column, so the test settings and the database width must
match. CI is consistent by construction: it runs on a fresh database, applies
migrations under the default OpenAI config (`halfvec(3072)`), then runs `pytest`.

Locally this can collide when the dev DB has been migrated to a local Ollama
width (e.g. `nomic-embed-text` → `halfvec(768)`): `pytest` defaults to OpenAI
(3072) and the integration tests fail with `asyncpg ... expected 768 dimensions,
not 3072`. Two ways to run green locally:

```bash
cd apps/api

# A) Match the tests to the Ollama dev DB (768):
WPRAG_EMBEDDING_PROVIDER=ollama WPRAG_OLLAMA_EMBED_DIMENSIONS=768 \
WPRAG_DATABASE_DSN=postgresql+asyncpg://wprag:wprag@localhost:5432/wprag \
  pytest

# B) Use a throwaway 3072 DB (CI-equivalent) and default settings:
#    point WPRAG_DATABASE_DSN at a fresh database, `alembic upgrade head`, then pytest.
```

Unit/config tests that assert the OpenAI **defaults** (3072) will conversely
fail if you force `WPRAG_EMBEDDING_PROVIDER=ollama` for the whole run — those are
env-default assertions, not bugs. Run the full suite with defaults against a
3072 DB, or scope the Ollama env to the integration modules only.

> All external calls (LLM, embeddings, GitHub, WordPress.org) are mocked or
> VCR-replayed — the suite never hits a live API.

## Common issues

| Symptom | Likely cause | Action |
|---|---|---|
| `/query` returns `degraded: true` | provider keys missing/invalid or outage | check `WPRAG_*_API_KEY`; the retrieval path still serves links |
| `/query` returns `declined: true` for known topics | corpus not ingested or below threshold | run ingestion; lower `WPRAG_SIMILARITY_THRESHOLD` if needed |
| 401 on admin calls | session cookie missing or expired | log in via `POST /api/v1/auth/login`; access token refreshes automatically via refresh cookie |
| 429 on `/query` | per-IP rate limit hit | tune `WPRAG_RATE_LIMIT_MAX_REQUESTS` / `WPRAG_RATE_LIMIT_WINDOW_SECONDS` |
| cost breaker refuses a call | projected cost over ceiling | raise `WPRAG_COST_CEILING_USD_PER_REQUEST` or shorten context |
| HNSW index won't build | pgvector < 0.7.0 | set `WPRAG_DIMENSIONALITY_MODE=vector_1536` and re-migrate |
| `pytest` fails `expected N dimensions, not M` | dev DB embedding width ≠ test settings | match settings to the DB width, or run against a fresh DB at the default width (see §5) |

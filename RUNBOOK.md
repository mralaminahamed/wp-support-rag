# Operator Runbook

**Project:** WP Plugin Support Desk RAG · **Author:** Al Amin Ahamed

Day-two operations: register a plugin, ingest its docs, query, and read metrics.
All admin calls require the bearer token from `WPRAG_ADMIN_BEARER_TOKEN`.

## 0. Generate the admin token

`WPRAG_ADMIN_BEARER_TOKEN` is an opaque, high-entropy secret (no fixed format);
the API compares the `Authorization` header to `Bearer <token>` exactly. Generate
one and supply it via the environment (never commit it — `.env` is git-ignored):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"   # or: openssl rand -base64 32
```

```bash
# local
echo "WPRAG_ADMIN_BEARER_TOKEN=<generated>" >> .env && docker compose up -d app
# production: set it in your secrets manager / host env before `up`
```

Rotate by changing the value and restarting. Without it, all `/api/v1/admin/*`
endpoints return 401.

## Session variables

```bash
export API=http://localhost:8000
export TOKEN=your-admin-bearer-token   # the value from step 0
```

## 1. Register a plugin

```bash
curl -sS -X POST "$API/api/v1/admin/plugins" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
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
curl -sS "$API/api/v1/admin/plugins" -H "Authorization: Bearer $TOKEN"
# → [{"slug":"swift-menu-duplicator","source_count":4,...}]
```

## 2. Ingest the documentation

```bash
curl -sS -X POST "$API/api/v1/admin/ingest/swift-menu-duplicator" \
  -H "Authorization: Bearer $TOKEN"
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
curl -sS "$API/api/v1/admin/plugins/swift-menu-duplicator/sources" \
  -H "Authorization: Bearer $TOKEN"
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
curl -sS "$API/api/v1/admin/metrics" -H "Authorization: Bearer $TOKEN"
# deflection_rate, helpful_rate, cache_hit_rate, degraded_rate, mean_cost_usd, p95_latency_ms

# Scope to one plugin:
curl -sS "$API/api/v1/admin/metrics?plugin_slug=swift-menu-duplicator" \
  -H "Authorization: Bearer $TOKEN"
```

Health and dependency reachability:

```bash
curl -sS "$API/health"   # status ok|degraded with per-dependency db/redis state
```

## Common issues

| Symptom | Likely cause | Action |
|---|---|---|
| `/query` returns `degraded: true` | provider keys missing/invalid or outage | check `WPRAG_*_API_KEY`; the retrieval path still serves links |
| `/query` returns `declined: true` for known topics | corpus not ingested or below threshold | run ingestion; lower `WPRAG_SIMILARITY_THRESHOLD` if needed |
| 401 on admin calls | wrong/missing bearer token | set `WPRAG_ADMIN_BEARER_TOKEN` and the `Authorization` header |
| 429 on `/query` | per-IP rate limit hit | tune `WPRAG_RATE_LIMIT_MAX_REQUESTS` / `WPRAG_RATE_LIMIT_WINDOW_SECONDS` |
| cost breaker refuses a call | projected cost over ceiling | raise `WPRAG_COST_CEILING_USD_PER_REQUEST` or shorten context |
| HNSW index won't build | pgvector < 0.7.0 | set `WPRAG_DIMENSIONALITY_MODE=vector_1536` and re-migrate |

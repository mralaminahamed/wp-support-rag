# Changelog

All notable changes to WP Plugin Support Desk RAG are documented here.

---

## [Unreleased]

### Added
- Setup wizard: first-run gate at `/setup` with 3 steps (generation provider, embeddings, first plugin); `system_settings` DB table; `GET /api/v1/admin/setup/status` + `POST /api/v1/admin/setup/complete`; setup complete banner on dashboard

### Planned
- Setup wizard implementation (spec at `docs/superpowers/specs/2026-06-01-setup-wizard-design.md`)

---

## [0.2.0] — 2026-06-01

### Added
- **Admin UI redesign** — Outfit Variable font, Tabler Icons webfont, navy sidebar (`#1a2744`), `#f1f5fb` page background, indigo primary (`oklch(0.53 0.22 279)`), 5-level text scale
- **New logo** — document + knowledge-graph mark (replaces generic chat bubble); unique gradient IDs per instance via `useId()`; updated `favicon.svg` to match
- **Nested sub-routes** — Settings (`/settings/generation`, `/settings/embeddings`) and Profile (`/profile/overview`, `/profile/security`, `/profile/permissions`) as URL-driven nested routes with `<Outlet />` and `Navigate` index redirects
- **ProfilePage** — Overview (avatar card + detail rows), Security (change-password form + session info), Permissions (grouped by namespace prefix); data passed via `useOutletContext<ProfileContext>()`
- **AuthLayout** — navy left panel with feature list and CSS grid-line texture; clean white right panel (no card wrapper); mobile logo fallback
- **HTTP-only cookie JWT auth** — access token (15 min) + refresh token (7 day, scoped to `/api/v1/auth/refresh`); no bearer tokens, no localStorage
- **User management** — create/invite/deactivate users; roles (`super_admin`, `admin`, `viewer`) + custom roles; per-user permission overrides (grant/revoke individual permissions)
- **Invite system** — `POST /api/v1/admin/users/{id}/invite` sends a 48 h invite link; `POST /api/v1/auth/accept-invite` sets password and activates account
- **Password reset flow** — `POST /api/v1/auth/forgot-password` emails a reset token; `POST /api/v1/auth/reset-password` validates and updates password; `PasswordResetToken` model with 1 h TTL
- **Email service** — `aiosmtplib`-based SMTP service (`apps/api/app/email.py`); invite, password reset, and welcome email templates
- **Dev seeders** — Laravel-style idempotent seeders for roles, users, plugins, and plugin registry; `uv run python -m app.cli` CLI entry point with `--table` and `--fresh` flags
- **CollapsibleSidebar** — `localStorage` persistence, `transition-[width] duration-200`, `w-14` collapsed / `w-54` expanded; profile NavLink at bottom with avatar + email + logout
- **Local network CORS** — `cors_origin_regex` field in `Settings`; nginx proxy passes `Origin` header; `GET /api/v1/admin/connection` removed (connection is always local nginx)
- **Ollama embedding support** — `nomic-embed-text` (768-dim `halfvec`); migration from `halfvec(3072)` to `halfvec(768)`; re-ingest triggered automatically after embedding config change
- **ConnectionBadge** — live API health indicator in topbar

### Removed
- **Connection tab** from Settings — nginx always proxies `/api/` to the backend; `VITE_API_BASE_URL` is always empty; tab was dead
- **Bearer token auth** — all admin routes switched to HTTP-only cookie sessions; `getApiBase`/`setApiBase` localStorage helpers removed

### Fixed
- Redis port collision: changed dev Redis port to `6380` (host) to avoid clashes with local Redis instances
- Ollama unreachable inside Docker at `localhost:11434` — use `host.docker.internal:11434` or mount `/usr/share/ollama/.ollama` volume for dockerized Ollama
- `text-embedding-3-large` produces `halfvec(3072)`; switching to `nomic-embed-text` (768-dim) requires migration — admin console now shows a dimension mismatch warning

---

## [0.1.0] — 2026-05-30

First working release.

### Phase 0 — Project scaffold
- Monorepo layout: `apps/api/`, `apps/admin/`, `apps/web/`, `config/plugins/`, `docs/`, `eval/`
- `docker-compose.yml` with PostgreSQL (pgvector), Redis, FastAPI, Celery worker/beat, nginx-served React admin console and widget
- Pydantic-settings configuration (`WPRAG_` prefix, repo-root `.env`)
- SQLAlchemy 2.0 async engine with `lru_cache` session factory

### Phase 1 — Database schema
- `plugins`, `sources`, `chunks`, `ingestion_runs`, `queries`, `feedback` tables with constraints and indices
- `halfvec(3072)` embedding column with HNSW index (`halfvec_cosine_ops`, m=16, ef_construction=64); GIN index on `content_tsv`
- Alembic async migrations with autogenerate

### Phase 2 — Ingestion pipeline
- GitHub ingestion: README, CHANGELOG, docs directory, issues (REST API)
- WordPress.org ingestion: FAQ, changelog, support threads (API + HTML scrape)
- Polite crawling with configurable delay (default 1 RPS); ETag/Last-Modified conditional requests
- Celery tasks with per-chunk content-hash skip; per-source isolation

### Phase 3 — Processing (chunking + embedding)
- Paragraph-boundary chunker with configurable target/max/overlap token counts
- `OpenAIEmbedder`: `text-embedding-3-large`, batched, exponential-backoff retry
- `OllamaEmbedder`: local models via Ollama REST API

### Phase 4 — Retrieval pipeline
- `retriever.py`: HNSW cosine vector search + Postgres FTS (`websearch_to_tsquery`), fused with Reciprocal Rank Fusion (k=60)
- Plugin centroid routing: queries without a slug rank plugins by centroid similarity; centroids cached in Redis (7-day TTL)
- `ef_search` tunable for recall/latency trade-off

### Phase 5 — Generation and safety
- Multi-provider LLM abstraction: Anthropic, OpenAI, Ollama; runtime Redis override; content-hash response cache; cost circuit breaker
- Citation validator: strips any URL not present in supplied chunks; LLM cannot fabricate source links
- `decline_gate`: rejects queries with no relevant chunks above similarity threshold
- Fail-open: returns degraded (links only) when LLM is unavailable
- Streaming via SSE (`/api/v1/query/stream`): `token` events + closing `done` event with citation-validated answer

### Phase 6 — API and initial admin console
- `POST /api/v1/query`, `POST /api/v1/query/stream`, `POST /api/v1/feedback`
- Admin API: plugins, sources, ingest, metrics, queries, LLM config
- Initial React admin console: Dashboard, Plugins, Playground (streaming), Settings
- Playwright e2e tests; 111 pytest tests passing

---

[Unreleased]: https://github.com/mralaminahamed/wp-support-rag/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/mralaminahamed/wp-support-rag/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/mralaminahamed/wp-support-rag/releases/tag/v0.1.0

# Contributing to WP Plugin Support Desk RAG

## Before you start

Read `docs/01-SRS.md` for the requirements (FR-*/NFR-* identifiers used in code comments) and `docs/02-Architecture.md` for architectural decisions (ADR-*).

The citation system is load-bearing: any change to retrieval, generation, or the citation validator requires the eval harness to pass before merge.

---

## Development setup

**Prerequisites:** Docker, Python 3.12+, Node.js 24+, pnpm, uv

```bash
git clone https://github.com/mralaminahamed/wp-support-rag.git
cd wp-support-rag

# Start infrastructure
docker compose up -d

# API
cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m app.cli          # seed dev fixtures (optional)

# Admin console
cd ../..
pnpm install
pnpm --filter @wp-support-rag/admin dev
```

---

## Quality gates

Every PR must pass locally before pushing:

```bash
# API (from apps/api/)
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app eval
uv run pytest -q

# Admin console (from repo root)
pnpm --filter @wp-support-rag/admin type-check
pnpm --filter @wp-support-rag/admin build
```

CI runs all gates on every push. The eval harness runs separately on changes to `app/prompts/`, `app/rag/`, or `eval/dataset/` and blocks regressions.

---

## Non-negotiable rules

These apply to every PR without exception:

1. **Citations come from the corpus, not the model.** The citation validator in `app/rag/citation.py` strips any URL not present in the retrieved chunk set. No new code path may bypass this.

2. **No stubs, no `# TODO`, no placeholders.** Every function body must be complete and runnable before merge.

3. **mypy --strict clean.** No `Any` escapes, no `# type: ignore` without a justifying comment referencing why the stub is absent.

4. **All runtime tunables in `config.py`.** No behavioural constant may be hard-coded elsewhere. Provider selection, retrieval weights, cache TTLs, and cost ceilings all originate in `Settings`.

5. **Every schema change needs an Alembic migration.** Never alter models without a corresponding migration file. The embedding dimension change rule is especially strict — changing providers requires a migration and full re-embed, not a config toggle.

6. **Auth cookie pattern only.** No new endpoints may accept bearer tokens or query-string credentials. All admin routes use the HTTP-only cookie JWT session established by `POST /api/v1/auth/login`.

---

## What belongs where

| Area | Location | Notes |
|---|---|---|
| Runtime tunables | `apps/api/app/config.py` | Never hard-code elsewhere |
| DB models | `apps/api/app/db/models.py` | Every schema change needs a migration |
| Prompt text | `apps/api/app/prompts/` | Versioned |
| Citation logic | `apps/api/app/rag/citation.py` | Only here |
| New LLM provider | `apps/api/app/llm/<name>.py` + `factory.py` | Thin: timeout, retry, error mapping |
| New source type | `apps/api/app/ingestion/` | Add fetcher + register in `tasks.py` |
| Admin UI pages | `apps/admin/src/pages/` | Follow existing NavLink + Outlet pattern |
| Shared UI components | `apps/admin/src/components/ui/` | shadcn base; Tabler icon strings |
| Plugin YAML configs | `config/plugins/` | See `config/README.md` for schema |

---

## Commit style

```
type(scope): short description

Longer explanation if needed. Reference requirement IDs:
- FR-GN-5: per-request cost breaker
- ADR-002: halfvec embedding dimension
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

---

## Pull request process

1. Branch from `main`. Name: `feat/<description>` or `fix/<description>`.
2. Run all quality gates locally.
3. For retrieval/generation changes, run `uv run python -m eval.harness` and paste the output in the PR description.
4. Reference the SRS requirement IDs your change implements or fixes.
5. One reviewer approval required before merge.

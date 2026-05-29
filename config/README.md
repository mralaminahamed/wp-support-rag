# Plugin registry (`config/plugins/`)

Declarative plugin registrations for the WP Plugin Support Desk RAG (FR-PM-5).
Each `*.yaml` file describes one plugin and the documentation **sources** to
ingest for it. The files are the source of truth; the database is reconciled
from them with the sync command below.

> Authoritative spec: `docs/01-SRS.md` (FR-PM-*, FR-IN-*) and
> `docs/02-Architecture.md` §2.2. Author: **Al Amin Ahamed**.

## File schema

```yaml
slug: swift-menu-duplicator          # required — unique registry key
name: Swift Menu Duplicator          # required — display name
wporg_slug: swift-menu-duplicator    # optional — enables wp.org sources
github_repo: mralaminahamed/swift-menu-duplicator  # optional — owner/name

sources:
  - source_type: github_readme
  - source_type: github_changelog
  - source_type: github_docs
    config:
      path: docs                     # repo subtree to crawl
  - source_type: github_issues
    config:
      state: closed                  # open | closed | all
      labels: [question, support]    # filter to support-relevant issues
      per_page: 50
  - source_type: wporg_faq
  - source_type: wporg_changelog
  - source_type: wporg_support
    config:
      max_threads: 10                # cap support threads pulled
```

- A plugin needs `github_repo` for any `github_*` source and `wporg_slug` for
  any `wporg_*` source.
- `config` is optional per source; omit it to use the adapter defaults.

### Source types

| Source type         | Backend      | Needs          |
| ------------------- | ------------ | -------------- |
| `github_readme`     | GitHub       | `github_repo`  |
| `github_changelog`  | GitHub       | `github_repo`  |
| `github_docs`       | GitHub       | `github_repo`  |
| `github_issues`     | GitHub       | `github_repo`  |
| `wporg_faq`         | WordPress.org| `wporg_slug`   |
| `wporg_changelog`   | WordPress.org| `wporg_slug`   |
| `wporg_support`     | WordPress.org| `wporg_slug`   |

Private GitHub repos and higher rate limits require `WPRAG_GITHUB_TOKEN`
(see `.env.example`).

## Syncing into the database

The registry is loaded by `app.ingestion.registry.load_plugin_config`. To
reconcile every file in this directory into the database:

```bash
cd apps/api
# from the host against the running stack (Postgres on localhost:5432)
WPRAG_DATABASE_DSN=postgresql+asyncpg://wprag:wprag@localhost:5432/wprag \
  python -m scripts.sync_plugins            # add/update declared plugins
WPRAG_DATABASE_DSN=… python -m scripts.sync_plugins --prune
# --prune also deletes DB plugins no longer declared here (cascades sources,
# documents, and chunks)
```

The sync is idempotent: a single-document change re-indexes only that
document's chunks (FR-PR-7). After syncing, trigger ingestion to populate the
corpus:

```bash
curl -X POST "$API/api/v1/admin/ingest" -H "Authorization: Bearer $TOKEN"
# or per plugin:
curl -X POST "$API/api/v1/admin/ingest/<slug>" -H "Authorization: Bearer $TOKEN"
```

## Adding a plugin

1. Create `config/plugins/<slug>.yaml` following the schema above.
2. Run `python -m scripts.sync_plugins` (see above).
3. Trigger ingestion for the new slug.

Only the author's own plugins belong here — the corpus must stay a grounded set
of first-party documentation.

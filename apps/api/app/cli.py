# Author: Al Amin Ahamed
"""WP Support RAG CLI.

Usage::

    # Seed all dev data
    uv run python -m app.cli seed

    # Seed only users
    uv run python -m app.cli seed --table users

    # Wipe and re-seed
    uv run python -m app.cli seed --fresh

    # Wipe and re-seed specific table
    uv run python -m app.cli seed --table plugins --fresh

    # Wipe all app data from the database (keeps schema and roles)
    uv run python -m app.cli clean

    # Wipe only plugins (sources, docs, chunks cascade)
    uv run python -m app.cli clean --scope plugins

    # Wipe users only
    uv run python -m app.cli clean --scope users

    # Pre-fetch all sources to disk cache (raw JSON + chunked JSONL)
    uv run python -m app.cli fetch

    # Fetch only one plugin
    uv run python -m app.cli fetch --plugin author-profile-blocks

    # Re-fetch even if cached
    uv run python -m app.cli fetch --force

    # Ingest from cache (no HTTP requests)
    uv run python -m app.cli ingest --from-cache

    # Ingest one plugin from cache
    uv run python -m app.cli ingest --plugin author-profile-blocks --from-cache
"""
from __future__ import annotations

import asyncio

import typer

app = typer.Typer(name="wprag", help="WP Support RAG CLI")


@app.command()
def seed(
    table: str = typer.Option(
        "all",
        help="Seeder name (roles|users|plugins) or 'all'.",
    ),
    fresh: bool = typer.Option(
        False,
        "--fresh",
        help="Truncate seeded rows before re-seeding (DESTRUCTIVE).",
    ),
    count: int = typer.Option(
        0,
        help="Per-seeder row count override (0 = seeder default).",
    ),
) -> None:
    """Seed sample development data (Laravel-style seeders)."""
    asyncio.run(_run_seed(table=table, fresh=fresh, count=count))


async def _run_seed(*, table: str, fresh: bool, count: int) -> None:
    from app.db.engine import dispose_engine, get_sessionmaker  # noqa: PLC0415
    from app.seeders.registry import SEEDERS, SEEDERS_BY_NAME  # noqa: PLC0415

    if table == "all":
        selected = SEEDERS
    elif table in SEEDERS_BY_NAME:
        selected = [SEEDERS_BY_NAME[table]]
    else:
        available = ["all", *SEEDERS_BY_NAME.keys()]
        typer.echo(f"Unknown table {table!r}. Available: {available}")
        raise typer.Exit(1)

    if fresh:
        typer.echo("⚠  --fresh: removing seeded rows (in reverse dep order)…")

    async with get_sessionmaker()() as db:
        if fresh:
            for cls in reversed(selected):
                inst = cls()
                if inst.truncate_sql:
                    typer.echo(f"  truncate: {inst.name}")
                    await inst.truncate(db)
            await db.commit()

        for cls in selected:
            inst = cls()
            typer.echo(f"→ seed {inst.name}…", nl=False)
            try:
                n = await inst.run(db, count=count)
                await db.commit()
                typer.echo(f" {n} rows")
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                typer.echo(f" FAILED: {exc}")
                raise typer.Exit(1) from exc

    typer.echo("✓ seed complete")
    await dispose_engine()


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------

_CLEAN_SCOPES = {
    "all": [
        # Remove all app data — schema and role/permission rows survive.
        # Cascade order: chunks → documents → sources → plugins, queries, users.
        "TRUNCATE TABLE chunks RESTART IDENTITY CASCADE",
        "TRUNCATE TABLE documents RESTART IDENTITY CASCADE",
        "TRUNCATE TABLE sources RESTART IDENTITY CASCADE",
        "TRUNCATE TABLE plugins RESTART IDENTITY CASCADE",
        "DELETE FROM thread_messages",
        "DELETE FROM threads",
        "TRUNCATE TABLE queries RESTART IDENTITY CASCADE",
        "DELETE FROM feedback",
        "DELETE FROM invite_tokens",
        "DELETE FROM user_roles",
        "DELETE FROM users",
        "DELETE FROM system_settings",
    ],
    "plugins": [
        # Wipe plugins and all dependent rows (sources/docs/chunks cascade).
        "TRUNCATE TABLE plugins RESTART IDENTITY CASCADE",
    ],
    "users": [
        "DELETE FROM invite_tokens",
        "DELETE FROM user_roles",
        "DELETE FROM users",
    ],
    "queries": [
        "DELETE FROM feedback",
        "DELETE FROM thread_messages",
        "DELETE FROM threads",
        "TRUNCATE TABLE queries RESTART IDENTITY CASCADE",
    ],
    "chunks": [
        "TRUNCATE TABLE chunks RESTART IDENTITY CASCADE",
    ],
}


@app.command()
def clean(
    scope: str = typer.Option(
        "all",
        help="What to wipe: all | plugins | users | queries | chunks.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt.",
    ),
) -> None:
    """Delete data from the database (schema and roles are preserved)."""
    if scope not in _CLEAN_SCOPES:
        typer.echo(f"Unknown scope {scope!r}. Available: {list(_CLEAN_SCOPES)}")
        raise typer.Exit(1)

    stmts = _CLEAN_SCOPES[scope]
    if not yes:
        typer.echo(f"⚠  This will run {len(stmts)} DELETE/TRUNCATE statement(s) for scope '{scope}'.")
        typer.confirm("Continue?", abort=True)

    asyncio.run(_run_clean(stmts=stmts, scope=scope))


async def _run_clean(*, stmts: list[str], scope: str) -> None:
    from sqlalchemy import text  # noqa: PLC0415

    from app.db.engine import dispose_engine, get_sessionmaker  # noqa: PLC0415

    async with get_sessionmaker()() as db:
        for stmt in stmts:
            try:
                await db.execute(text(stmt))
            except Exception:  # noqa: BLE001
                # Table may not exist in older migrations — skip gracefully.
                pass
        await db.commit()

    typer.echo(f"✓ clean '{scope}' complete")
    await dispose_engine()


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

_DEFAULT_CACHE = "./data/fetch_cache"


@app.command()
def fetch(
    plugin: str = typer.Option("all", "--plugin", "-p", help="Plugin slug or 'all'."),
    source_type: str = typer.Option("all", "--source-type", "-t", help="Source type or 'all'."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Re-fetch even if raw is already cached."
    ),
    no_process: bool = typer.Option(False, "--no-process", help="Skip normalize+chunk step."),
    cache_dir: str = typer.Option(_DEFAULT_CACHE, "--cache-dir", help="Cache root directory."),
) -> None:
    """Pre-fetch all external sources to disk cache (raw JSON + chunked JSONL).

    On subsequent runs omit --force to skip already-cached documents.
    Use 'ingest --from-cache' to ingest without hitting external URLs.
    """
    asyncio.run(
        _run_fetch(
            plugin=plugin,
            source_type=source_type,
            force=force,
            no_process=no_process,
            cache_dir=cache_dir,
        )
    )


async def _run_fetch(
    *, plugin: str, source_type: str, force: bool, no_process: bool, cache_dir: str
) -> None:
    from sqlalchemy import select  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415
    from app.db.engine import dispose_engine, get_sessionmaker  # noqa: PLC0415
    from app.db.models import Plugin, Source  # noqa: PLC0415
    from app.ingestion.adapter_registry import build_registry  # noqa: PLC0415
    from app.ingestion.adapters.base import SourceContext  # noqa: PLC0415
    from app.ingestion.fetch_cache import FetchCache  # noqa: PLC0415
    from app.processing.chunker import chunk_document  # noqa: PLC0415
    from app.ingestion.normalize import normalize  # noqa: PLC0415

    settings = get_settings()
    cache = FetchCache(cache_dir)
    sm = get_sessionmaker()
    registry = await build_registry(sm)

    async with sm() as session:
        q = select(Source, Plugin).join(Plugin, Plugin.id == Source.plugin_id).where(
            Source.enabled.is_(True)
        )
        if plugin != "all":
            q = q.where(Plugin.slug == plugin)
        if source_type != "all":
            q = q.where(Source.source_type == source_type)
        rows = (await session.execute(q)).all()

    typer.echo(f"→ {len(rows)} source(s) to process  cache={cache_dir}")

    total_fetched = total_skipped = total_chunks = 0

    for source, plg in rows:
        adapter = registry.get(source.source_type)
        if adapter is None:
            typer.echo(f"  skip (no adapter): {plg.slug}/{source.source_type}")
            continue

        ctx = SourceContext(
            plugin_slug=plg.slug,
            source_type=source.source_type,
            github_repo=plg.github_repo,
            wporg_slug=plg.wporg_slug,
            config=dict(source.config),
        )
        source_id = str(source.id)
        typer.echo(f"  [{plg.slug}/{source.source_type}]", nl=False)

        try:
            doc_count = 0
            async for raw in adapter.fetch(ctx):
                if not force and cache.has_raw(source_id, raw.external_id):
                    total_skipped += 1
                    doc_count += 1
                    continue
                cache.save_raw(source_id, raw)
                total_fetched += 1
                doc_count += 1

                if not no_process:
                    normalized = normalize(raw.content, raw.content_type)
                    chunks = chunk_document(
                        normalized,
                        plugin_slug=plg.slug,
                        doc_type=raw.doc_type,
                        source_url=raw.source_url,
                        version=raw.version,
                        settings=settings,
                    )
                    cache.save_chunks(source_id, raw.external_id, chunks)
                    total_chunks += len(chunks)

            typer.echo(f" {doc_count} doc(s)")
        except Exception as exc:  # noqa: BLE001
            typer.echo(f" FAILED: {exc}")

    stats = cache.stats()
    typer.echo(
        f"\n✓ fetch done  fetched={total_fetched} skipped(cached)={total_skipped}"
        f" chunks={total_chunks}"
    )
    typer.echo(
        f"  cache: {stats['sources']} source(s), {stats['raw_docs']} raw doc(s),"
        f" {stats['chunk_files']} chunk file(s)"
    )
    await dispose_engine()


# ---------------------------------------------------------------------------
# ingest (direct, with optional cache read)
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    plugin: str = typer.Option("all", "--plugin", "-p", help="Plugin slug or 'all'."),
    source_type: str = typer.Option("all", "--source-type", "-t", help="Source type or 'all'."),
    from_cache: bool = typer.Option(
        False, "--from-cache", help="Load raw docs from disk cache instead of HTTP."
    ),
    cache_dir: str = typer.Option(_DEFAULT_CACHE, "--cache-dir", help="Cache root directory."),
) -> None:
    """Ingest sources directly (bypasses Celery).

    With --from-cache, reads pre-fetched RawDocuments from disk instead of
    making HTTP requests, then chunks, embeds, and writes to the database.
    """
    asyncio.run(
        _run_ingest(
            plugin=plugin,
            source_type=source_type,
            from_cache=from_cache,
            cache_dir=cache_dir,
        )
    )


async def _run_ingest(
    *, plugin: str, source_type: str, from_cache: bool, cache_dir: str
) -> None:
    from sqlalchemy import select  # noqa: PLC0415

    from app.config import get_settings  # noqa: PLC0415
    from app.db.engine import dispose_engine, get_sessionmaker  # noqa: PLC0415
    from app.db.models import Plugin, Source  # noqa: PLC0415
    from app.ingestion.adapter_registry import build_registry  # noqa: PLC0415
    from app.ingestion.adapters.base import SourceContext  # noqa: PLC0415
    from app.ingestion.fetch_cache import FetchCache  # noqa: PLC0415
    from app.ingestion.tasks import ingest_source  # noqa: PLC0415

    cache = FetchCache(cache_dir) if from_cache else None
    sm = get_sessionmaker()
    registry = await build_registry(sm)

    async with sm() as session:
        q = select(Source, Plugin).join(Plugin, Plugin.id == Source.plugin_id).where(
            Source.enabled.is_(True)
        )
        if plugin != "all":
            q = q.where(Plugin.slug == plugin)
        if source_type != "all":
            q = q.where(Source.source_type == source_type)
        rows = (await session.execute(q)).all()

    typer.echo(f"→ {len(rows)} source(s)  from_cache={from_cache}")

    for source, plg in rows:
        typer.echo(f"  [{plg.slug}/{source.source_type}]", nl=False)
        if from_cache and cache:
            cached_docs = cache.list_raw(str(source.id))
            if not cached_docs:
                typer.echo(" no cache — skipping (run 'fetch' first)")
                continue
            typer.echo(f" {len(cached_docs)} cached doc(s) … ", nl=False)

        summary = await ingest_source(
            source.id,
            adapter=(
                _CachedAdapter(cache, str(source.id), registry.get(source.source_type))
                if from_cache and cache
                else None
            ),
            sessionmaker=sm,
        )
        typer.echo(
            f"new={summary.documents_new} updated={summary.documents_updated}"
            f" unchanged={summary.documents_unchanged} status={summary.status}"
        )

    typer.echo("✓ ingest done")
    await dispose_engine()


class _CachedAdapter:
    """Wraps an adapter to yield cached RawDocuments instead of making HTTP requests."""

    handles: tuple[str, ...]

    def __init__(self, cache: "FetchCache", source_id: str, real_adapter: object) -> None:
        from app.ingestion.fetch_cache import FetchCache  # noqa: PLC0415

        self._cache = cache
        self._source_id = source_id
        self._real = real_adapter
        self.handles = getattr(real_adapter, "handles", ())

    async def fetch(self, ctx: object):  # type: ignore[override]
        docs = self._cache.list_raw(self._source_id)
        for doc in docs:
            yield doc


if __name__ == "__main__":
    app()

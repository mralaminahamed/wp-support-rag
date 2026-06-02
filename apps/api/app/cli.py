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


if __name__ == "__main__":
    app()

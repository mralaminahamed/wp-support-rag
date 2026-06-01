# Author: Al Amin Ahamed
"""WP Support RAG CLI.

Usage::

    # Seed all dev data
    uv run python -m app.cli

    # Seed only users
    uv run python -m app.cli --table users

    # Wipe and re-seed
    uv run python -m app.cli --fresh

    # Wipe and re-seed specific table
    uv run python -m app.cli --table plugins --fresh
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


if __name__ == "__main__":
    app()

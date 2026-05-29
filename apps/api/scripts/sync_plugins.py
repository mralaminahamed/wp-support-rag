r"""Sync declarative plugin registrations into the database (FR-PM-5).

Loads every ``config/plugins/*.yaml`` via
:func:`app.ingestion.registry.load_plugin_config` so the registry matches the
declared set. Idempotent: re-running reconciles existing plugins and their
sources. With ``--prune``, plugins present in the database but no longer declared
in the config directory are deleted (cascading to their sources, documents, and
chunks).

Usage::

    WPRAG_DATABASE_DSN=postgresql+asyncpg://wprag:wprag@localhost:5432/wprag \\
        python -m scripts.sync_plugins [--prune] [CONFIG_DIR]

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.db.engine import dispose_engine, get_sessionmaker
from app.db.models import Plugin
from app.ingestion.registry import load_plugin_config, parse_plugin_config
from sqlalchemy import delete, select

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config" / "plugins"


async def sync_plugins(paths: list[Path], declared: set[str], *, prune: bool) -> None:
    """Reconcile the database registry against the declared plugin set.

    Args:
        paths: Resolved plugin config file paths, in load order.
        declared: Slugs declared across ``paths`` (used for pruning).
        prune: When True, delete database plugins whose slug is not in ``declared``.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        for path in paths:
            plugin = await load_plugin_config(session, path)
            print(f"synced  {plugin.slug}")

        if prune:
            existing = (await session.execute(select(Plugin.slug))).scalars().all()
            stale = sorted(set(existing) - declared)
            for slug in stale:
                await session.execute(delete(Plugin).where(Plugin.slug == slug))
                print(f"pruned  {slug}")

        await session.commit()

    print(f"\n{len(paths)} plugins declared")
    await dispose_engine()


def main() -> None:
    """Parse arguments, scan the config directory, and run the sync.

    Raises:
        FileNotFoundError: If the config directory does not exist.
    """
    parser = argparse.ArgumentParser(description="Sync plugin registrations from config files.")
    parser.add_argument(
        "config_dir",
        nargs="?",
        default=str(_DEFAULT_CONFIG_DIR),
        help="Directory of plugin YAML files (default: repo config/plugins).",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete database plugins not declared in the config directory.",
    )
    args = parser.parse_args()
    config_dir = Path(args.config_dir)
    if not config_dir.is_dir():
        raise FileNotFoundError(f"config directory not found: {config_dir}")
    paths = sorted(config_dir.glob("*.yaml"))
    declared = {parse_plugin_config(path).slug for path in paths}
    asyncio.run(sync_plugins(paths, declared, prune=args.prune))


if __name__ == "__main__":
    main()

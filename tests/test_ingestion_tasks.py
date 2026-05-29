"""Ingestion task integration tests (DB): landing, hash-skip, failure isolation.

Exercises the real ingestion path against a live database, with WordPress.org
mocked by a VCR cassette. Skips when no migrated database is reachable.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from app.db.engine import get_sessionmaker
from app.db.models import Document, IngestionRun, Source
from app.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError
from app.ingestion.registry import add_source, create_plugin
from app.ingestion.tasks import ingest_source
from sqlalchemy import select

from tests.conftest import play

SLUG = "swift-menu-duplicator"


class _RaisingAdapter:
    """Adapter that always fails, used to force a single-source failure."""

    handles = ("github_issues",)

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Raise immediately to simulate an unrecoverable upstream failure."""
        raise SourceFetchError("forced failure")
        yield  # pragma: no cover - unreachable, marks this an async generator


async def _make_plugin(
    slug: str, source_types: list[str]
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Create a plugin with the given sources and return their ids."""
    async with get_sessionmaker()() as session:
        plugin = await create_plugin(
            session,
            slug=slug,
            name="Swift Menu Duplicator",
            wporg_slug=SLUG,
            github_repo=f"mralaminahamed/{SLUG}",
        )
        ids: dict[str, uuid.UUID] = {}
        for source_type in source_types:
            source = await add_source(session, plugin_id=plugin.id, source_type=source_type)
            ids[source_type] = source.id
        await session.commit()
        return plugin.id, ids


async def _doc_types(plugin_id: uuid.UUID) -> set[str]:
    """Return the distinct document types stored for a plugin."""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Document.doc_type).where(Document.plugin_id == plugin_id)
        )
        return set(rows.scalars().all())


async def test_two_source_types_land_then_rerun_creates_zero_new(clean_plugins: None) -> None:
    """Two source types land; a re-run with unchanged content adds nothing (FR-IN-5)."""
    plugin_id, ids = await _make_plugin("phase2-smd", ["wporg_faq", "wporg_changelog"])

    with play("wporg_plugin_info.yaml"):
        first = [await ingest_source(ids["wporg_faq"]), await ingest_source(ids["wporg_changelog"])]

    assert all(s.status == "succeeded" for s in first)
    assert all(s.documents_new == 1 for s in first)
    assert await _doc_types(plugin_id) == {"wporg_faq", "wporg_changelog"}

    with play("wporg_plugin_info.yaml"):
        second = [
            await ingest_source(ids["wporg_faq"]),
            await ingest_source(ids["wporg_changelog"]),
        ]

    assert all(s.documents_new == 0 for s in second)
    assert all(s.documents_unchanged == 1 for s in second)

    async with get_sessionmaker()() as session:
        doc_count = len(
            (await session.execute(select(Document.id).where(Document.plugin_id == plugin_id)))
            .scalars()
            .all()
        )
    assert doc_count == 2


async def test_single_source_failure_leaves_siblings_succeeded(clean_plugins: None) -> None:
    """A forced failure in one source does not affect a sibling (FR-IN-7)."""
    plugin_id, ids = await _make_plugin("phase2-iso", ["wporg_faq", "github_issues"])

    with play("wporg_plugin_info.yaml"):
        ok = await ingest_source(ids["wporg_faq"])
    failed = await ingest_source(ids["github_issues"], adapter=_RaisingAdapter())

    assert ok.status == "succeeded" and ok.documents_new == 1
    assert failed.status == "failed" and failed.error

    async with get_sessionmaker()() as session:
        runs = (
            await session.execute(
                select(IngestionRun.status, Source.source_type)
                .join(Source, Source.id == IngestionRun.source_id)
                .where(Source.plugin_id == plugin_id)
            )
        ).all()
    by_type = {source_type: status for status, source_type in runs}
    assert by_type == {"wporg_faq": "succeeded", "github_issues": "failed"}
    assert await _doc_types(plugin_id) == {"wporg_faq"}

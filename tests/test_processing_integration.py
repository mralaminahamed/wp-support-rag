"""Processing pipeline integration tests (DB): indexing, re-index isolation, centroid.

Runs the full fetch -> chunk -> embed -> index path against a live database with
WordPress.org mocked by VCR cassettes and embeddings produced by a fake client.
Skips when no migrated database is reachable.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid

from app.config import get_settings
from app.db.engine import get_sessionmaker
from app.db.models import Chunk, Document
from app.db.redis import get_redis
from app.ingestion.registry import add_source, create_plugin
from app.ingestion.tasks import ingest_source
from app.processing.centroid import get_plugin_centroid
from sqlalchemy import select

from tests.conftest import FakeEmbeddingClient, play

SLUG = "swift-menu-duplicator"


async def _make_plugin() -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """Create a plugin with FAQ and changelog sources; return their ids."""
    async with get_sessionmaker()() as session:
        plugin = await create_plugin(session, slug="phase2-proc", name="SMD", wporg_slug=SLUG)
        faq = await add_source(session, plugin_id=plugin.id, source_type="wporg_faq")
        chl = await add_source(session, plugin_id=plugin.id, source_type="wporg_changelog")
        await session.commit()
        return plugin.id, {"wporg_faq": faq.id, "wporg_changelog": chl.id}


async def _chunk_ids(plugin_id: uuid.UUID, doc_type: str) -> set[uuid.UUID]:
    """Return the chunk ids for a plugin's document of the given type."""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.plugin_id == plugin_id, Document.doc_type == doc_type)
        )
        return set(rows.scalars().all())


async def test_ingestion_populates_chunks_with_embedding_and_tsv(clean_plugins: None) -> None:
    """After ingestion, chunks carry non-null embeddings and content_tsv (FR-PR-5/6)."""
    plugin_id, ids = await _make_plugin()
    client = FakeEmbeddingClient(get_settings().embedding_dimensions)

    with play("wporg_plugin_info.yaml"):
        faq = await ingest_source(ids["wporg_faq"], embedding_client=client)
        chl = await ingest_source(ids["wporg_changelog"], embedding_client=client)

    assert faq.status == "succeeded" and chl.status == "succeeded"

    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(
                    Chunk.embedding, Chunk.content_tsv, Chunk.token_count, Chunk.heading_path
                ).where(Chunk.plugin_id == plugin_id)
            )
        ).all()

    assert rows, "expected chunks to be created"
    cap = get_settings().chunk_max_tokens
    for embedding, tsv, token_count, _heading in rows:
        assert embedding is not None
        assert tsv  # generated tsvector is non-empty (FR-PR-6)
        assert 0 < token_count <= cap  # caps respected (FR-PR-2)


async def test_reindex_changed_document_leaves_siblings_untouched(clean_plugins: None) -> None:
    """Re-indexing one changed document replaces only its chunks (FR-PR-7)."""
    plugin_id, ids = await _make_plugin()
    client = FakeEmbeddingClient(get_settings().embedding_dimensions)

    with play("wporg_plugin_info.yaml"):
        await ingest_source(ids["wporg_faq"], embedding_client=client)
        await ingest_source(ids["wporg_changelog"], embedding_client=client)

    faq_before = await _chunk_ids(plugin_id, "wporg_faq")
    changelog_before = await _chunk_ids(plugin_id, "wporg_changelog")
    assert faq_before and changelog_before

    # v2: FAQ content changed, changelog identical.
    with play("wporg_plugin_info_v2.yaml"):
        faq = await ingest_source(ids["wporg_faq"], embedding_client=client)
        chl = await ingest_source(ids["wporg_changelog"], embedding_client=client)

    assert faq.documents_updated == 1
    assert chl.documents_unchanged == 1

    faq_after = await _chunk_ids(plugin_id, "wporg_faq")
    changelog_after = await _chunk_ids(plugin_id, "wporg_changelog")

    assert faq_after.isdisjoint(faq_before)  # changed doc's chunks replaced
    assert changelog_after == changelog_before  # sibling untouched


async def test_centroid_cached_after_ingestion(clean_plugins: None) -> None:
    """A plugin centroid is computed and cached in Redis (ADR-004)."""
    plugin_id, ids = await _make_plugin()
    client = FakeEmbeddingClient(get_settings().embedding_dimensions)

    with play("wporg_plugin_info.yaml"):
        await ingest_source(ids["wporg_faq"], embedding_client=client)

    centroid = await get_plugin_centroid(get_redis(), plugin_id)
    assert centroid is not None
    assert len(centroid) == get_settings().embedding_dimensions

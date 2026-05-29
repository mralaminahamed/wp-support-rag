"""Database integration test: chunk insert and HNSW cosine retrieval.

Exercises the real schema against a live PostgreSQL + pgvector instance. The
test is skipped automatically when no migrated database is reachable, so the
unit suite stays runnable without infrastructure; CI provisions a pgvector
service and runs ``alembic upgrade head`` before invoking pytest.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid

import pytest
from app.config import get_settings
from app.db.engine import get_engine, get_sessionmaker
from app.db.models import Chunk, Document, Plugin, Source
from sqlalchemy import select, text


async def _schema_ready() -> bool:
    """Report whether a migrated database is reachable.

    Returns:
        bool: ``True`` if the ``chunks`` table can be queried.
    """
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1 FROM chunks LIMIT 0"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.asyncio


async def test_chunk_roundtrip_via_hnsw_cosine() -> None:
    """A synthetic chunk inserts and is retrieved by an HNSW cosine query.

    The whole exchange runs inside a single transaction that is rolled back, so
    the test leaves no rows behind. ``hnsw.ef_search`` is set from configuration
    to drive the index path (NFR-PT-2 / FR-PR-5).
    """
    if not await _schema_ready():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")

    settings = get_settings()
    dims = settings.embedding_dimensions
    embedding = [0.1] * dims
    suffix = uuid.uuid4().hex[:8]

    async with get_sessionmaker()() as session:
        await session.execute(text(f"SET LOCAL hnsw.ef_search = {settings.ef_search}"))

        plugin = Plugin(slug=f"itest-{suffix}", name="Integration Test Plugin")
        session.add(plugin)
        await session.flush()

        source = Source(plugin_id=plugin.id, source_type="github_readme")
        session.add(source)
        await session.flush()

        document = Document(
            source_id=source.id,
            plugin_id=plugin.id,
            external_id=f"README-{suffix}",
            doc_type="github_readme",
            content_hash="deadbeef",
            source_url="https://example.com/readme",
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(
            document_id=document.id,
            plugin_id=plugin.id,
            chunk_index=0,
            content="Installation requires PHP 8.1 and WordPress 6.0 or newer.",
            heading_path="Installation > Requirements",
            token_count=11,
            embedding=embedding,
        )
        session.add(chunk)
        await session.flush()

        nearest = await session.execute(
            select(Chunk.id).order_by(Chunk.embedding.cosine_distance(embedding)).limit(1)
        )
        assert nearest.scalar_one() == chunk.id

        # The generated lexical column must populate from content (FR-PR-6).
        tsv = await session.execute(select(Chunk.content_tsv).where(Chunk.id == chunk.id))
        assert tsv.scalar_one()

        await session.rollback()

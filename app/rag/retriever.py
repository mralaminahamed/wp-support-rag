"""Hybrid retrieval (ADR-003).

Combines a vector HNSW cosine search with a Postgres full-text search and merges
the two ranked lists with Reciprocal Rank Fusion (FR-QR-3). The vector search is
scoped by plugin when the plugins are known and uses the configured query-time
``ef_search``; the lexical search uses ``websearch_to_tsquery`` ranked by
``ts_rank_cd``. A minimum vector-similarity threshold (FR-QR-6) filters
vector-only candidates, and the top ``k`` chunks are returned with their source
URLs and scores (FR-QR-5).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Chunk, Document


class RetrievedChunk(BaseModel):
    """A retrieved chunk with provenance and scores (FR-QR-5).

    Attributes:
        chunk_id: The chunk's id.
        document_id: The owning document's id.
        plugin_id: The owning plugin's id.
        content: The chunk text.
        heading_path: Heading breadcrumb, if any.
        source_url: Canonical source URL for citation.
        score: Fused Reciprocal Rank Fusion score (ranking key).
        vector_similarity: Cosine similarity (1 - distance) if in the vector list.
        vector_rank: 1-based rank in the vector list, if present.
        lexical_rank: 1-based rank in the lexical list, if present.
    """

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    plugin_id: uuid.UUID
    content: str
    heading_path: str | None
    source_url: str
    score: float
    vector_similarity: float | None = None
    vector_rank: int | None = None
    lexical_rank: int | None = None


@dataclass(frozen=True)
class _Hit:
    """An internal single-list search hit."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    plugin_id: uuid.UUID
    content: str
    heading_path: str | None
    source_url: str
    component_score: float


def _scope(stmt: Select[Any], plugin_ids: Sequence[uuid.UUID] | None) -> Select[Any]:
    """Apply a plugin-id scope to a select statement when ids are given.

    Args:
        stmt: The select statement to scope.
        plugin_ids: Plugin ids to filter by, or ``None``/empty for no scope.

    Returns:
        Select[Any]: The scoped (or unchanged) statement.
    """
    if plugin_ids:
        return stmt.where(Chunk.plugin_id.in_(list(plugin_ids)))
    return stmt


async def vector_search(
    session: AsyncSession,
    embedding: list[float],
    plugin_ids: Sequence[uuid.UUID] | None,
    settings: Settings,
) -> list[_Hit]:
    """Run an HNSW cosine search for the query embedding.

    Args:
        session: Active async session.
        embedding: The query embedding vector.
        plugin_ids: Plugin scope, or ``None`` to search all plugins.
        settings: Application settings (``ef_search``, ``retrieval_top_n``).

    Returns:
        list[_Hit]: Hits ordered nearest first; ``component_score`` is cosine similarity.
    """
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.ef_search)}"))
    distance = Chunk.embedding.cosine_distance(embedding).label("distance")
    stmt = (
        _scope(
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.plugin_id,
                Chunk.content,
                Chunk.heading_path,
                Document.source_url,
                distance,
            ).join(Document, Document.id == Chunk.document_id),
            plugin_ids,
        )
        .order_by(distance)
        .limit(settings.retrieval_top_n)
    )

    hits: list[_Hit] = []
    for chunk_id, document_id, plugin_id, content, heading_path, source_url, dist in (
        await session.execute(stmt)
    ).all():
        hits.append(
            _Hit(
                chunk_id,
                document_id,
                plugin_id,
                content,
                heading_path,
                source_url,
                float(1.0 - dist),
            )
        )
    return hits


async def lexical_search(
    session: AsyncSession,
    query: str,
    plugin_ids: Sequence[uuid.UUID] | None,
    settings: Settings,
) -> list[_Hit]:
    """Run a full-text search ranked by ``ts_rank_cd``.

    Args:
        session: Active async session.
        query: The raw user query.
        plugin_ids: Plugin scope, or ``None`` to search all plugins.
        settings: Application settings (``retrieval_top_n``).

    Returns:
        list[_Hit]: Hits ordered best first; ``component_score`` is the ts_rank.
    """
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(Chunk.content_tsv, tsquery).label("rank")
    stmt = (
        _scope(
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.plugin_id,
                Chunk.content,
                Chunk.heading_path,
                Document.source_url,
                rank,
            ).join(Document, Document.id == Chunk.document_id),
            plugin_ids,
        )
        .where(Chunk.content_tsv.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(settings.retrieval_top_n)
    )

    hits: list[_Hit] = []
    for chunk_id, document_id, plugin_id, content, heading_path, source_url, score in (
        await session.execute(stmt)
    ).all():
        hits.append(
            _Hit(chunk_id, document_id, plugin_id, content, heading_path, source_url, float(score))
        )
    return hits


def _fuse(
    vector_hits: list[_Hit], lexical_hits: list[_Hit], settings: Settings
) -> list[RetrievedChunk]:
    """Merge two ranked lists with Reciprocal Rank Fusion (ADR-003).

    Args:
        vector_hits: Vector hits, nearest first.
        lexical_hits: Lexical hits, best first.
        settings: Application settings (``rrf_k`` and per-list weights).

    Returns:
        list[RetrievedChunk]: Fused chunks sorted by descending fused score.
    """
    k = settings.rrf_k
    merged: dict[uuid.UUID, RetrievedChunk] = {}

    for rank, hit in enumerate(vector_hits, start=1):
        merged[hit.chunk_id] = RetrievedChunk(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            plugin_id=hit.plugin_id,
            content=hit.content,
            heading_path=hit.heading_path,
            source_url=hit.source_url,
            score=settings.vector_weight / (k + rank),
            vector_similarity=hit.component_score,
            vector_rank=rank,
        )

    for rank, hit in enumerate(lexical_hits, start=1):
        contribution = settings.lexical_weight / (k + rank)
        existing = merged.get(hit.chunk_id)
        if existing is None:
            merged[hit.chunk_id] = RetrievedChunk(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                plugin_id=hit.plugin_id,
                content=hit.content,
                heading_path=hit.heading_path,
                source_url=hit.source_url,
                score=contribution,
                lexical_rank=rank,
            )
        else:
            existing.score += contribution
            existing.lexical_rank = rank

    fused = list(merged.values())
    fused.sort(key=lambda chunk: chunk.score, reverse=True)
    return fused


def _passes_threshold(chunk: RetrievedChunk, threshold: float) -> bool:
    """Report whether a fused chunk clears the minimum-score threshold (FR-QR-6).

    A lexical match (exact term overlap) is always kept; a vector-only chunk is
    kept only when its cosine similarity meets the threshold.

    Args:
        chunk: The fused chunk.
        threshold: Minimum vector similarity.

    Returns:
        bool: ``True`` if the chunk should be retained.
    """
    if chunk.lexical_rank is not None:
        return True
    return chunk.vector_similarity is not None and chunk.vector_similarity >= threshold


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    embedding: list[float],
    *,
    plugin_ids: Sequence[uuid.UUID] | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Retrieve fused, thresholded candidates for a query (FR-QR-3/5/6).

    Each retrieval signal is skipped when its weight is zero, so disabling a
    signal still yields usable results from the other (ADR-003 robustness).

    Args:
        session: Active async session.
        query: The raw user query.
        embedding: The query embedding vector.
        plugin_ids: Plugin scope, or ``None`` for all plugins.
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        list[RetrievedChunk]: Thresholded chunks sorted by fused score.
    """
    settings = settings or get_settings()
    vector_hits = (
        await vector_search(session, embedding, plugin_ids, settings)
        if settings.vector_weight > 0
        else []
    )
    lexical_hits = (
        await lexical_search(session, query, plugin_ids, settings)
        if settings.lexical_weight > 0
        else []
    )
    fused = _fuse(vector_hits, lexical_hits, settings)
    return [chunk for chunk in fused if _passes_threshold(chunk, settings.similarity_threshold)]

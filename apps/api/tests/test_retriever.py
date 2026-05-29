"""Unit tests for RRF fusion, thresholding, routing math, and reranking."""

from __future__ import annotations

import uuid

from apps.api.config import Settings
from apps.api.rag.reranker import LexicalOverlapReranker
from apps.api.rag.retriever import RetrievedChunk, _fuse, _Hit, _passes_threshold
from apps.api.rag.router import cosine_similarity


def _hit(score: float) -> _Hit:
    return _Hit(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="text",
        heading_path=None,
        source_url="https://example.com",
        component_score=score,
    )


def test_rrf_rewards_chunks_in_both_lists() -> None:
    """A chunk ranked by both signals outranks single-list chunks (ADR-003)."""
    shared = _hit(0.9)
    vector = [shared, _hit(0.8)]
    lexical = [shared, _hit(0.5)]

    fused = _fuse(vector, lexical, Settings())

    assert fused[0].chunk_id == shared.chunk_id
    assert fused[0].vector_rank == 1 and fused[0].lexical_rank == 1
    assert fused[0].score > fused[1].score


def test_threshold_keeps_lexical_drops_low_vector_only() -> None:
    """Lexical hits survive; vector-only hits below the threshold are dropped."""
    lexical_only = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="c",
        heading_path=None,
        source_url="u",
        score=0.1,
        lexical_rank=1,
    )
    weak_vector = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="c",
        heading_path=None,
        source_url="u",
        score=0.1,
        vector_similarity=0.05,
        vector_rank=1,
    )
    strong_vector = weak_vector.model_copy(update={"vector_similarity": 0.9})

    assert _passes_threshold(lexical_only, 0.15)
    assert not _passes_threshold(weak_vector, 0.15)
    assert _passes_threshold(strong_vector, 0.15)


def test_cosine_similarity_basics() -> None:
    """Cosine similarity is 1 for identical vectors and 0 for orthogonal ones."""
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0], [0.0]) == 0.0


async def test_lexical_overlap_reranker_orders_by_overlap() -> None:
    """The reranker promotes the candidate sharing more terms with the query."""
    low = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="unrelated payment gateway text",
        heading_path=None,
        source_url="u",
        score=0.9,
    )
    high = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="duplicate the navigation menu with submenu items",
        heading_path=None,
        source_url="u",
        score=0.1,
    )
    ordered = await LexicalOverlapReranker().rerank(
        "duplicate navigation menu submenu", [low, high]
    )

    assert ordered[0].chunk_id == high.chunk_id

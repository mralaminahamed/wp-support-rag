"""Optional rerank stage (FR-QR-4).

A config-gated stage that reorders the fused candidate set. Reranking is disabled
by default to control cost and enabled for the eval suite to measure its lift
(§2.4). The default reranker is a deterministic lexical-overlap scorer that needs
no network or model, standing in for a hosted cross-encoder behind the
:class:`Reranker` protocol so a stronger backend can be swapped in by config.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.rag.retriever import RetrievedChunk

_WORD_RE = re.compile(r"\w+")


@runtime_checkable
class Reranker(Protocol):
    """Reorders fused candidates by relevance to the query."""

    async def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Return the candidates reordered by descending relevance.

        Args:
            query: The user query.
            candidates: The fused candidate chunks.

        Returns:
            list[RetrievedChunk]: The reordered candidates.
        """
        ...


class LexicalOverlapReranker:
    """Deterministic offline reranker scoring token overlap with the query."""

    async def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Reorder candidates by query/term overlap, stable on ties.

        Args:
            query: The user query.
            candidates: The fused candidate chunks.

        Returns:
            list[RetrievedChunk]: Candidates sorted by descending overlap, then
            by their original fused score.
        """
        query_terms = set(_WORD_RE.findall(query.lower()))

        def overlap(chunk: RetrievedChunk) -> int:
            return len(query_terms & set(_WORD_RE.findall(chunk.content.lower())))

        return sorted(candidates, key=lambda chunk: (overlap(chunk), chunk.score), reverse=True)


def build_reranker(settings: Settings | None = None) -> Reranker | None:
    """Return the configured reranker, or ``None`` when disabled (FR-QR-4).

    Args:
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        Reranker | None: A reranker when ``rerank_enabled`` is set, else ``None``.
    """
    settings = settings or get_settings()
    return LexicalOverlapReranker() if settings.rerank_enabled else None

"""Optional rerank stage (FR-QR-4).

A config-gated stage that reorders the fused candidate set. Reranking is disabled
by default to control cost and enabled for the eval suite to measure its lift
(§2.4).

The default reranker is BM25 (Okapi BM25), a probabilistic term-frequency model
that significantly outperforms simple word-overlap scoring. It rewards chunks that
contain rare query terms (IDF component) and applies length normalisation so short,
dense chunks are not penalised against long ones. No external model or network call
is required.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.rag.retriever import RetrievedChunk

_WORD_RE = re.compile(r"\w+")

# BM25 hyper-parameters (Robertson & Zaragoza 2009 recommended defaults).
_BM25_K1 = 1.5   # term-frequency saturation
_BM25_B = 0.75   # length normalisation strength


def _tokenise(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


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


class BM25Reranker:
    """Offline BM25 reranker — no network, no external model.

    Scores each candidate chunk against the query using Okapi BM25, then
    breaks ties with the fused RRF score so the original retrieval signal
    remains as a secondary sort key.
    """

    async def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Reorder candidates by BM25 score, tiebreak on fused score.

        Args:
            query: The user query.
            candidates: The fused candidate chunks.

        Returns:
            list[RetrievedChunk]: Candidates sorted by descending BM25 score.
        """
        if not candidates:
            return candidates

        query_terms = _tokenise(query)
        if not query_terms:
            return candidates

        # Tokenise all chunks once.
        tokenised = [_tokenise(c.content) for c in candidates]
        doc_lengths = [len(toks) for toks in tokenised]
        avgdl = sum(doc_lengths) / len(doc_lengths)
        n = len(candidates)

        # Precompute per-term document frequency across the candidate set.
        df: Counter[str] = Counter()
        for toks in tokenised:
            for term in set(toks):
                df[term] += 1

        def idf(term: str) -> float:
            # Smooth IDF — never negative.
            return math.log(1.0 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))

        def bm25(toks: list[str], dl: int) -> float:
            tf_map: Counter[str] = Counter(toks)
            score = 0.0
            for term in query_terms:
                tf = tf_map.get(term, 0)
                numerator = tf * (_BM25_K1 + 1)
                denominator = tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl)
                score += idf(term) * numerator / denominator
            return score

        scored = [
            (bm25(toks, dl), chunk)
            for toks, dl, chunk in zip(tokenised, doc_lengths, candidates)
        ]
        scored.sort(key=lambda pair: (pair[0], pair[1].score), reverse=True)
        return [chunk for _, chunk in scored]


def build_reranker(settings: Settings | None = None) -> Reranker | None:
    """Return the configured reranker, or ``None`` when disabled (FR-QR-4).

    Args:
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        Reranker | None: A BM25 reranker when ``rerank_enabled`` is set, else ``None``.
    """
    settings = settings or get_settings()
    return BM25Reranker() if settings.rerank_enabled else None

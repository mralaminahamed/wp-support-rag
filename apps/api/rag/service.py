"""Retrieval orchestration entry point.

Ties routing, hybrid retrieval, and optional reranking into one call used by the
eval harness, tests, and (in later phases) the generation path. Given a query and
an optional plugin slug, it embeds the query once, scopes retrieval to the slug or
to the routed plugin(s) (FR-QR-1/2), runs hybrid retrieval (FR-QR-3), applies the
optional rerank stage (FR-QR-4), and returns the top-k chunks (FR-QR-5).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import Settings, get_settings
from apps.api.ingestion.registry import get_plugin_by_slug
from apps.api.processing.embedder import EmbeddingClient, embed_texts
from apps.api.rag.reranker import build_reranker
from apps.api.rag.retriever import RetrievedChunk, hybrid_retrieve
from apps.api.rag.router import route_query


class RetrievalResult(BaseModel):
    """The outcome of a retrieval request.

    Attributes:
        query: The original query text.
        plugin_ids: Plugin ids retrieval was scoped to (empty if unscoped).
        routed: Whether the plugin scope came from centroid routing (FR-QR-2).
        chunks: The top-k retrieved chunks (FR-QR-5).
    """

    query: str
    plugin_ids: list[uuid.UUID] = Field(default_factory=list)
    routed: bool = False
    chunks: list[RetrievedChunk] = Field(default_factory=list)


async def retrieve(
    session: AsyncSession,
    redis: Redis,
    embedding_client: EmbeddingClient,
    query: str,
    *,
    plugin_slug: str | None = None,
    settings: Settings | None = None,
) -> RetrievalResult:
    """Route, retrieve, optionally rerank, and return top-k chunks (FR-QR-1..6).

    Args:
        session: Active async session.
        redis: Async Redis client (for centroid routing).
        embedding_client: Client used to embed the query.
        query: The free-text question.
        plugin_slug: Optional plugin filter; routing runs when omitted.
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        RetrievalResult: The scope used and the top-k retrieved chunks.
    """
    settings = settings or get_settings()
    embedding = (await embed_texts(embedding_client, [query], settings))[0]

    routed = False
    if plugin_slug is not None:
        plugin = await get_plugin_by_slug(session, plugin_slug)
        plugin_ids: list[uuid.UUID] = [plugin.id] if plugin is not None else []
    else:
        plugin_ids = await route_query(session, redis, embedding, settings)
        routed = True

    scope = plugin_ids or None
    candidates = await hybrid_retrieve(
        session, query, embedding, plugin_ids=scope, settings=settings
    )

    reranker = build_reranker(settings)
    if reranker is not None:
        candidates = await reranker.rerank(query, candidates)

    return RetrievalResult(
        query=query,
        plugin_ids=plugin_ids,
        routed=routed,
        chunks=candidates[: settings.retrieval_top_k],
    )

"""Public query and feedback endpoints (FR-DL-1, FR-FB-1/2).

The query endpoint runs the full route -> retrieve -> generate path, persists a
query record with its observability fields (FR-FB-1), and returns the cited
answer with a query id. The feedback endpoint binds a helpful/not-helpful rating
to that query (FR-FB-2). Both are CORS-enabled and per-IP rate-limited.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_embedding_client,
    get_provider,
    get_redis_dep,
    get_settings_dep,
    rate_limit,
)
from app.api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    QueryRequest,
    QueryResponse,
    SourceRef,
)
from app.config import Settings
from app.db.engine import get_session
from app.db.models import Feedback, Query
from app.llm.base import LLMProvider
from app.llm.circuit_breaker import CostCircuitBreaker
from app.processing.embedder import EmbeddingClient
from app.prompts.registry import get_registry
from app.rag.generator import StreamEvent, generate, generate_stream
from app.rag.retriever import RetrievedChunk
from app.rag.service import retrieve

router = APIRouter(prefix="/api/v1", tags=["query"])


def _sse(event: str, data: dict[str, object]) -> str:
    """Format a Server-Sent Events frame.

    Args:
        event: The SSE event name.
        data: JSON-serialisable payload.

    Returns:
        str: The encoded SSE frame.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sources(chunks: list[RetrievedChunk], citations: set[str]) -> list[SourceRef]:
    """Build de-duplicated source references for the widget.

    Args:
        chunks: The retrieved chunks.
        citations: URLs the answer cited.

    Returns:
        list[SourceRef]: One reference per distinct source URL.
    """
    seen: dict[str, SourceRef] = {}
    for chunk in chunks:
        if chunk.source_url not in seen:
            seen[chunk.source_url] = SourceRef(
                url=chunk.source_url,
                heading_path=chunk.heading_path,
                cited=chunk.source_url in citations,
            )
    return list(seen.values())


@router.post("/query", response_model=QueryResponse)
async def query(
    payload: QueryRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
    embedder: EmbeddingClient = Depends(get_embedding_client),
    provider: LLMProvider = Depends(get_provider),
    ip_hash: str = Depends(rate_limit),
) -> QueryResponse:
    """Answer a question and log the query (FR-DL-1, FR-FB-1).

    Args:
        payload: The query request.
        session: Database session.
        redis: Redis client.
        settings: Application settings.
        embedder: Embedding client.
        provider: LLM provider.
        ip_hash: Hashed caller IP from the rate limiter (NFR-SC-5).

    Returns:
        QueryResponse: The answer, citations, sources, and query id.
    """
    start = perf_counter()
    result = await retrieve(
        session,
        redis,
        embedder,
        payload.question,
        plugin_slug=payload.plugin_slug,
        settings=settings,
    )
    generation = await generate(redis, provider, payload.question, result.chunks, settings=settings)
    latency_ms = int((perf_counter() - start) * 1000)

    plugin_id = None
    if result.plugin_ids:
        plugin_id = result.plugin_ids[0]
    elif result.chunks:
        plugin_id = result.chunks[0].plugin_id

    cost = None
    if generation.usage is not None:
        cost = Decimal(
            str(
                CostCircuitBreaker(settings).estimate_cost(
                    generation.usage.input_tokens, generation.usage.output_tokens
                )
            )
        )

    record = Query(
        plugin_id=plugin_id,
        query_text=payload.question,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in result.chunks],
        response_text=generation.answer,
        provider=provider.name,
        prompt_version=generation.prompt_version,
        tokens_in=generation.usage.input_tokens if generation.usage else None,
        tokens_out=generation.usage.output_tokens if generation.usage else None,
        cost_usd=cost,
        cached=generation.cached,
        degraded=generation.degraded,
        latency_ms=latency_ms,
        ip_hash=ip_hash,
    )
    session.add(record)
    await session.commit()

    citations = set(generation.citations)
    return QueryResponse(
        query_id=record.id,
        answer=generation.answer,
        citations=generation.citations,
        sources=_sources(result.chunks, citations),
        cached=generation.cached,
        degraded=generation.degraded,
        declined=generation.declined,
        plugin_slug=payload.plugin_slug,
        latency_ms=latency_ms,
    )


@router.post("/query/stream")
async def query_stream(
    payload: QueryRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
    embedder: EmbeddingClient = Depends(get_embedding_client),
    provider: LLMProvider = Depends(get_provider),
    ip_hash: str = Depends(rate_limit),
) -> StreamingResponse:
    """Stream a cited answer as Server-Sent Events (FR-DL-3).

    Emits ``token`` events as the answer is generated and a closing ``done``
    event carrying the citation-validated answer, sources, and the logged query
    id. The query is persisted after the stream completes (FR-FB-1).

    Args:
        payload: The query request.
        session: Database session.
        redis: Redis client.
        settings: Application settings.
        embedder: Embedding client.
        provider: LLM provider.
        ip_hash: Hashed caller IP from the rate limiter (NFR-SC-5).

    Returns:
        StreamingResponse: A ``text/event-stream`` response.
    """
    start = perf_counter()
    result = await retrieve(
        session,
        redis,
        embedder,
        payload.question,
        plugin_slug=payload.plugin_slug,
        settings=settings,
    )

    async def event_source() -> AsyncIterator[str]:
        final: StreamEvent | None = None
        async for event in generate_stream(
            redis, provider, payload.question, result.chunks, settings=settings
        ):
            if event.type == "token":
                yield _sse("token", {"text": event.text})
            else:
                final = event
        assert final is not None
        latency_ms = int((perf_counter() - start) * 1000)

        plugin_id = None
        if result.plugin_ids:
            plugin_id = result.plugin_ids[0]
        elif result.chunks:
            plugin_id = result.chunks[0].plugin_id
        cost = None
        if final.usage is not None:
            cost = Decimal(
                str(
                    CostCircuitBreaker(settings).estimate_cost(
                        final.usage.input_tokens, final.usage.output_tokens
                    )
                )
            )
        record = Query(
            plugin_id=plugin_id,
            query_text=payload.question,
            retrieved_chunk_ids=[chunk.chunk_id for chunk in result.chunks],
            response_text=final.answer,
            provider=provider.name,
            prompt_version=get_registry().active("support_answer").version,
            tokens_in=final.usage.input_tokens if final.usage else None,
            tokens_out=final.usage.output_tokens if final.usage else None,
            cost_usd=cost,
            cached=final.cached,
            degraded=final.degraded,
            latency_ms=latency_ms,
            ip_hash=ip_hash,
        )
        session.add(record)
        await session.commit()

        citations = set(final.citations)
        yield _sse(
            "done",
            {
                "query_id": str(record.id),
                "answer": final.answer or "",
                "citations": final.citations,
                "sources": [s.model_dump() for s in _sources(result.chunks, citations)],
                "cached": final.cached,
                "degraded": final.degraded,
                "declined": final.declined,
                "latency_ms": latency_ms,
            },
        )

    return StreamingResponse(event_source(), media_type="text/event-stream")


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    payload: FeedbackRequest,
    session: AsyncSession = Depends(get_session),
    _ip_hash: str = Depends(rate_limit),
) -> FeedbackResponse:
    """Record helpful/not-helpful feedback bound to a query (FR-FB-2).

    Args:
        payload: The feedback request.
        session: Database session.
        _ip_hash: Hashed caller IP from the rate limiter.

    Returns:
        FeedbackResponse: Acknowledgement of the recorded feedback.

    Raises:
        HTTPException: 404 if the referenced query does not exist.
    """
    if await session.get(Query, payload.query_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="query not found")
    session.add(Feedback(query_id=payload.query_id, rating=payload.rating, comment=payload.comment))
    await session.commit()
    return FeedbackResponse()

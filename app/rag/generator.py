"""Grounded generation orchestration (§2.5, FR-GN-1/6/7/8).

Wraps a provider call in the fixed cross-cutting order: cache lookup -> cost
circuit breaker -> provider -> citation validation -> cache store. On any
provider failure it fails open and returns the retrieved chunks with their links
and a degraded notice (FR-GN-6); on empty retrieval it declines and points the
user to a support request (FR-GN-7). Only source URLs of supplied chunks may be
cited (FR-GN-8).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.llm.base import CompletionRequest, LLMProvider, ProviderError, TokenUsage
from app.llm.cache import CachedAnswer, ResponseCache, cache_key
from app.llm.circuit_breaker import CostCircuitBreaker
from app.llm.factory import active_model
from app.prompts.registry import get_registry
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

DECLINE_MESSAGE = (
    "I don't have documentation that answers this question. Please open a support "
    "request and a maintainer will help you directly."
)
DEGRADED_NOTICE = (
    "The answer service is temporarily unavailable, so here are the most relevant "
    "documentation passages with links. Please review them directly."
)


class GenerationResult(BaseModel):
    """The outcome of a generation request.

    Attributes:
        answer: The answer text (or decline/degraded notice).
        citations: Source URLs cited; always a subset of supplied chunk URLs.
        chunks: The chunks supplied to the model (echoed for the UI/links).
        model: Model id used (empty for decline).
        prompt_version: Active prompt version used.
        cached: Whether the answer was served from cache.
        degraded: Whether fail-open degraded mode was used (FR-GN-6).
        declined: Whether the decline path was taken (FR-GN-7).
        usage: Token usage when a live call occurred, else ``None``.
    """

    answer: str
    citations: list[str] = Field(default_factory=list)
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    model: str
    prompt_version: str
    cached: bool = False
    degraded: bool = False
    declined: bool = False
    usage: TokenUsage | None = None


def validate_citations(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Strip fabricated URLs and return the cited allowed URLs (FR-GN-8).

    Any URL emitted by the model that is not the source URL of a supplied chunk
    is removed from the answer text; the remaining cited URLs are returned.

    Args:
        text: The model's answer text.
        allowed: The set of source URLs of supplied chunks.

    Returns:
        tuple[str, list[str]]: The cleaned text and the sorted cited URLs.
    """
    cited: set[str] = set()
    cleaned = text
    for match in _URL_RE.findall(text):
        url = match.rstrip(".,;:)]}")
        if url in allowed:
            cited.add(url)
        else:
            cleaned = cleaned.replace(match, "")
    return cleaned, sorted(cited)


async def generate(
    redis: Redis,
    provider: LLMProvider,
    query: str,
    chunks: list[RetrievedChunk],
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> GenerationResult:
    """Generate a grounded, cited answer with caching and fail-open (FR-GN-*).

    Args:
        redis: Async Redis client for the response cache.
        provider: The resolved LLM provider.
        query: The user question.
        chunks: The retrieved chunks supplying the grounded context.
        model: Model id; resolved from configuration if omitted.
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        GenerationResult: The answer (or decline/degraded notice) and citations.

    Raises:
        CostCeilingExceeded: If the request is projected to exceed the ceiling.
    """
    settings = settings or get_settings()
    model = model or active_model(settings)
    prompt = get_registry().active("support_answer")

    if not chunks:
        logger.info("generation declined: empty retrieval", extra={"declined": True})
        return GenerationResult(
            answer=DECLINE_MESSAGE, model="", prompt_version=prompt.version, declined=True
        )

    cache = ResponseCache(redis, settings.response_cache_ttl_seconds)
    key = cache_key(query, [chunk.chunk_id for chunk in chunks], model, prompt.version)

    hit = await cache.get(key)
    if hit is not None:
        return GenerationResult(
            answer=hit.answer,
            citations=hit.citations,
            chunks=chunks,
            model=hit.model,
            prompt_version=hit.prompt_version,
            cached=True,
            usage=TokenUsage(input_tokens=hit.input_tokens, output_tokens=hit.output_tokens),
        )

    request = CompletionRequest(
        system=prompt.system,
        user=prompt.render(query, chunks),
        model=model,
        max_tokens=settings.llm_max_output_tokens,
    )
    CostCircuitBreaker(settings).guard(request)

    try:
        result = await provider.complete(request)
    except ProviderError as exc:
        logger.warning(
            "generation degraded: provider failure", extra={"degraded": True, "error": str(exc)}
        )
        return GenerationResult(
            answer=DEGRADED_NOTICE,
            citations=_ordered_unique(chunk.source_url for chunk in chunks),
            chunks=chunks,
            model=model,
            prompt_version=prompt.version,
            degraded=True,
        )

    cleaned, citations = validate_citations(result.text, {chunk.source_url for chunk in chunks})
    await cache.set(
        key,
        CachedAnswer(
            answer=cleaned,
            citations=citations,
            model=result.model,
            prompt_version=prompt.version,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        ),
    )
    return GenerationResult(
        answer=cleaned,
        citations=citations,
        chunks=chunks,
        model=result.model,
        prompt_version=prompt.version,
        usage=result.usage,
    )


def _ordered_unique(urls: Iterable[str]) -> list[str]:
    """Return URLs de-duplicated while preserving first-seen order.

    Args:
        urls: An iterable of URL strings.

    Returns:
        list[str]: De-duplicated URLs in order.
    """
    seen: dict[str, None] = {}
    for url in urls:
        seen.setdefault(url, None)
    return list(seen)

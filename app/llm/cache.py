"""Content-hash response cache (FR-GN-4).

Caches answers in Redis keyed on
``sha256(normalised_query | ordered_retrieved_chunk_ids | model | prompt_version)``.
Because the key includes the ordered chunk ids, any change to the retrieved
context (for example after re-indexing) naturally invalidates stale answers.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence

from pydantic import BaseModel
from redis.asyncio import Redis


class CachedAnswer(BaseModel):
    """A cached generation result.

    Attributes:
        answer: The generated answer text.
        citations: Source URLs cited (all from supplied chunks).
        model: Model id that produced the answer.
        prompt_version: Active prompt version used.
        input_tokens: Prompt tokens consumed.
        output_tokens: Completion tokens generated.
    """

    answer: str
    citations: list[str]
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int


def cache_key(query: str, chunk_ids: Sequence[uuid.UUID], model: str, prompt_version: str) -> str:
    """Compute the response cache key (FR-GN-4).

    Args:
        query: The raw user query (normalised here).
        chunk_ids: Ordered ids of chunks supplied to the model.
        model: Model id.
        prompt_version: Active prompt version.

    Returns:
        str: The namespaced Redis key.
    """
    normalised = " ".join(query.lower().split())
    fingerprint = ",".join(str(chunk_id) for chunk_id in chunk_ids)
    raw = f"{normalised}|{fingerprint}|{model}|{prompt_version}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"answer:{digest}"


class ResponseCache:
    """Redis-backed response cache with a configurable TTL."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        """Initialise the cache.

        Args:
            redis: Async Redis client.
            ttl_seconds: Time-to-live for cached answers.
        """
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> CachedAnswer | None:
        """Return the cached answer for a key, if present.

        Args:
            key: The cache key.

        Returns:
            CachedAnswer | None: The cached answer, or ``None`` on a miss.
        """
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return CachedAnswer.model_validate_json(raw)

    async def set(self, key: str, answer: CachedAnswer) -> None:
        """Store an answer under a key with the configured TTL.

        Args:
            key: The cache key.
            answer: The answer to cache.
        """
        await self._redis.set(key, answer.model_dump_json(), ex=self._ttl)

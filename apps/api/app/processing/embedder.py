"""Batched embedding and atomic per-document indexing.

Embeds chunk text with ``text-embedding-3-large`` in batches of at most 100 texts
per call (FR-PR-4) with bounded retry and backoff, then writes a document's chunks
in one transaction so re-indexing replaces only that document's chunks (FR-PR-7).
The requested embedding width follows the configured dimensionality mode (ADR-002).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from openai import AsyncOpenAI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Chunk, Document
from app.processing.chunker import ChunkData

logger = logging.getLogger(__name__)


class EmbeddingUnavailable(Exception):  # noqa: N818 - parallels provider error naming
    """The embedding backend is not usable for a configuration reason.

    Raised when the embedding provider has no credentials, so it can be
    distinguished from transient failures and mapped to a clear 503 rather than
    retried or surfaced as an opaque 500.
    """


@runtime_checkable
class EmbeddingClient(Protocol):
    """Minimal embedding backend the pipeline depends on.

    Implementations embed a batch of texts and return one vector per text. The
    batch is already capped by the caller; the implementation applies its own
    network concerns.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Texts to embed (already within the per-call cap).

        Returns:
            list[list[float]]: One embedding vector per input text, in order.
        """
        ...


class OpenAIEmbeddingClient:
    """Embedding client backed by the OpenAI embeddings API (FR-PR-4)."""

    def __init__(self, settings: Settings) -> None:
        """Initialise the client from configuration.

        Args:
            settings: Application settings supplying model, key, and dimensions.
        """
        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        # Build the SDK client only when a key is present; constructing it without
        # one raises eagerly, which would surface as an opaque 500 during request
        # dependency resolution. A missing key becomes a clear EmbeddingUnavailable
        # at call time instead (see embed).
        self._client = AsyncOpenAI(api_key=key) if key else None
        self._model = settings.embed_model
        self._dimensions = settings.embedding_dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch via the OpenAI API at the configured dimensionality.

        Args:
            texts: Texts to embed.

        Returns:
            list[list[float]]: One embedding per text.

        Raises:
            EmbeddingUnavailable: If no OpenAI API key is configured.
        """
        if self._client is None:
            raise EmbeddingUnavailable(
                "OpenAI embeddings are not configured; set WPRAG_OPENAI_API_KEY"
            )
        response = await self._client.embeddings.create(
            model=self._model, input=texts, dimensions=self._dimensions
        )
        return [item.embedding for item in response.data]


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    """Construct the configured embedding client.

    Args:
        settings: Application settings.

    Returns:
        EmbeddingClient: The OpenAI-backed client.
    """
    return OpenAIEmbeddingClient(settings)


async def _embed_batch_with_retry(
    client: EmbeddingClient, batch: list[str], settings: Settings
) -> list[list[float]]:
    """Embed one batch with bounded exponential backoff.

    Args:
        client: The embedding client.
        batch: Texts to embed (within the per-call cap).
        settings: Application settings (retry ceiling).

    Returns:
        list[list[float]]: Embeddings for the batch.

    Raises:
        Exception: The last error if all attempts fail.
    """
    last_error: Exception | None = None
    for attempt in range(settings.http_max_retries + 1):
        try:
            return await client.embed(batch)
        except EmbeddingUnavailable:
            raise  # configuration error: not transient, do not retry
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised below
            last_error = exc
            if attempt >= settings.http_max_retries:
                break
            delay = min(2.0**attempt, 60.0)
            logger.warning("retrying embedding batch", extra={"attempt": attempt, "delay_s": delay})
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error


async def embed_texts(
    client: EmbeddingClient, texts: Sequence[str], settings: Settings
) -> list[list[float]]:
    """Embed many texts, batched at the configured cap (FR-PR-4).

    Args:
        client: The embedding client.
        texts: All texts to embed.
        settings: Application settings (batch size, retries).

    Returns:
        list[list[float]]: One embedding per input text, in input order.
    """
    batch_size = settings.embed_batch_size
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = list(texts[start : start + batch_size])
        vectors.extend(await _embed_batch_with_retry(client, batch, settings))
    return vectors


async def index_document_chunks(
    session: AsyncSession,
    document: Document,
    chunks: Sequence[ChunkData],
    vectors: Sequence[list[float]],
) -> int:
    """Replace a document's chunks atomically (FR-PR-7).

    Deletes the document's existing chunks and inserts the new ones within the
    caller's transaction, so a re-index touches only this document's chunks and
    leaves sibling documents untouched.

    Args:
        session: Active async session (committed by the caller).
        document: The owning document.
        chunks: The chunk data to persist.
        vectors: Embedding vectors aligned with ``chunks``.

    Returns:
        int: Number of chunks written.

    Raises:
        ValueError: If ``chunks`` and ``vectors`` differ in length.
    """
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    for chunk, vector in zip(chunks, vectors, strict=True):
        session.add(
            Chunk(
                document_id=document.id,
                plugin_id=document.plugin_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                heading_path=chunk.heading_path,
                token_count=chunk.token_count,
                embedding=vector,
                meta=chunk.metadata,
            )
        )
    return len(chunks)

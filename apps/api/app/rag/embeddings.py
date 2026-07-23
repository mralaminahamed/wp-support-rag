"""LangChain ``Embeddings`` adapter over the app's embedding pipeline.

Wraps :mod:`app.processing.embedder` so ``langchain-postgres`` (and any other
LangChain component) can embed through the exact same code path the legacy
pipeline uses — preserving provider switching (OpenAI/Ollama), the configured
dimensionality binding, and the ``EmbeddingUnavailable`` → 503 contract.

The app is fully async; only the ``aembed_*`` methods are implemented. The sync
methods are required by the :class:`Embeddings` ABC but raise, so an accidental
sync call fails loudly instead of silently blocking the event loop.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.config import Settings
from app.processing.embedder import build_embedding_client, embed_texts


class WpragEmbeddings(Embeddings):
    """Adapt :func:`app.processing.embedder.embed_texts` to LangChain.

    Args:
        settings: Application settings selecting the embedding provider, model,
            and vector width.
    """

    def __init__(self, settings: Settings) -> None:
        """Build the underlying embedding client for the configured provider.

        Args:
            settings: Application settings selecting provider, model, and width.
        """
        self._settings = settings
        self._client = build_embedding_client(settings)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents (batched at the configured cap).

        Args:
            texts: Document texts to embed.

        Returns:
            list[list[float]]: One vector per input text, in order.
        """
        return await embed_texts(self._client, texts, self._settings)

    async def aembed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Args:
            text: The query text.

        Returns:
            list[float]: The query embedding.
        """
        return (await embed_texts(self._client, [text], self._settings))[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Not supported — this adapter is async-only.

        Raises:
            NotImplementedError: Always; use :meth:`aembed_documents`.
        """
        raise NotImplementedError("WpragEmbeddings is async-only; use aembed_documents")

    def embed_query(self, text: str) -> list[float]:
        """Not supported — this adapter is async-only.

        Raises:
            NotImplementedError: Always; use :meth:`aembed_query`.
        """
        raise NotImplementedError("WpragEmbeddings is async-only; use aembed_query")

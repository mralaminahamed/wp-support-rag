"""Tests for batched embedding with retry (FR-PR-4)."""

from __future__ import annotations

import pytest

from apps.api.config import Settings
from apps.api.processing import embedder
from apps.api.processing.embedder import embed_texts
from apps.api.tests.conftest import FakeEmbeddingClient


async def test_batches_respect_the_configured_cap() -> None:
    """Texts are embedded in batches no larger than embed_batch_size."""
    settings = Settings(embed_batch_size=3)
    client = FakeEmbeddingClient(dimensions=4)
    texts = [f"text-{i}" for i in range(7)]

    vectors = await embed_texts(client, texts, settings)

    assert len(vectors) == 7
    assert all(len(v) == 4 for v in vectors)
    assert client.batch_sizes == [3, 3, 1]
    assert max(client.batch_sizes) <= settings.embed_batch_size


async def test_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient embedding failure is retried within the bounded ceiling."""

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(embedder.asyncio, "sleep", _no_sleep)
    settings = Settings(embed_batch_size=10, http_max_retries=2)

    class _FlakyClient:
        def __init__(self) -> None:
            self.attempts = 0

        async def embed(self, texts: list[str]) -> list[list[float]]:
            self.attempts += 1
            if self.attempts < 2:
                raise RuntimeError("transient")
            return [[0.5] for _ in texts]

    client = _FlakyClient()
    vectors = await embed_texts(client, ["a", "b"], settings)

    assert client.attempts == 2
    assert vectors == [[0.5], [0.5]]


async def test_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persistent failures raise after exhausting the retry ceiling."""

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(embedder.asyncio, "sleep", _no_sleep)
    settings = Settings(http_max_retries=1)

    class _DeadClient:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("down")

    with pytest.raises(RuntimeError, match="down"):
        await embed_texts(_DeadClient(), ["a"], settings)

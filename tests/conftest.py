"""Shared test fixtures.

Provides a VCR configured for fully offline replay (no live calls), a database
availability gate that skips integration tests when no migrated database is
reachable, and a cleanup fixture that removes plugins created by tests.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
import vcr
from app.db.engine import get_sessionmaker
from app.db.models import Plugin
from sqlalchemy import delete, or_, text

CASSETTE_DIR = Path(__file__).parent / "cassettes"
TEST_SLUG_PREFIX = "phase2-"

# Offline VCR: never record, match on the request path. An unmatched request
# raises, proving no live calls reach GitHub or WordPress.org.
offline_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTE_DIR),
    record_mode="none",
    match_on=["method", "scheme", "host", "path"],
)


class FakeEmbeddingClient:
    """Deterministic offline embedding client for tests (no live API calls)."""

    def __init__(self, dimensions: int) -> None:
        """Initialise with the target vector width and a call recorder."""
        self.dimensions = dimensions
        self.batch_sizes: list[int] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one distinct, non-zero vector per text and record the batch size."""
        self.batch_sizes.append(len(texts))
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        """Build a deterministic non-null vector keyed on the text."""
        vector = [0.001] * self.dimensions
        vector[len(text) % self.dimensions] = 1.0
        return vector


class BoWEmbeddingClient:
    """Deterministic bag-of-words embedding client for retrieval/routing tests.

    Each token maps to a stable dimension via a content hash, so cosine
    similarity reflects shared vocabulary — enough to make vector search and
    centroid routing meaningful offline without a real embedding model.
    """

    _TOKEN = re.compile(r"[a-z0-9]+")

    def __init__(self, dimensions: int) -> None:
        """Initialise with the target vector width."""
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one bag-of-words vector per text."""
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        """Accumulate a hashed bag-of-words vector for the text."""
        vector = [0.0] * self.dimensions
        for token in self._TOKEN.findall(text.lower()):
            index = int.from_bytes(hashlib.blake2s(token.encode()).digest()[:4], "big")
            vector[index % self.dimensions] += 1.0
        return vector


def play(cassette_name: str) -> Any:
    """Return an offline cassette context allowing repeated playback.

    Repeats are allowed because some interactions are replayed more than once
    (e.g. FAQ and changelog share one Plugin API endpoint, and re-run tests
    replay it again).

    Args:
        cassette_name: File name under the cassette directory.

    Returns:
        Any: A context manager that activates the cassette.
    """
    return offline_vcr.use_cassette(cassette_name, allow_playback_repeats=True)


@pytest.fixture(autouse=True)
def _fresh_pooled_clients() -> Iterator[None]:
    """Rebuild the cached engine/Redis clients per test.

    Each async test runs on its own event loop; a pooled engine cached from a
    prior test is bound to that test's now-closed loop and would fail. Clearing
    the memoised factories ensures every test builds clients on its own loop.

    Yields:
        None: Control to the test body.
    """
    from app.db.engine import get_engine, get_sessionmaker
    from app.db.redis import get_redis

    for cached in (get_engine, get_sessionmaker, get_redis):
        cached.cache_clear()
    yield
    for cached in (get_engine, get_sessionmaker, get_redis):
        cached.cache_clear()


async def database_available() -> bool:
    """Report whether a migrated database is reachable.

    Returns:
        bool: ``True`` if the ``documents`` table can be queried.
    """
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1 FROM documents LIMIT 0"))
        return True
    except Exception:
        return False


@pytest.fixture
async def clean_plugins() -> AsyncIterator[None]:
    """Remove test plugins (slug prefix ``phase2-``) before and after a test."""
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")

    async def _purge() -> None:
        async with get_sessionmaker()() as session:
            await session.execute(
                delete(Plugin).where(
                    or_(
                        Plugin.slug.like(f"{TEST_SLUG_PREFIX}%"),
                        Plugin.slug == "swift-menu-duplicator",
                    )
                )
            )
            await session.commit()

    await _purge()
    yield
    await _purge()

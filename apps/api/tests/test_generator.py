"""Generator orchestration tests: grounding, caching, fail-open, decline, breaker.

Uses a fake provider and the live Redis cache (skips when Redis is unreachable).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import logging
import uuid

import pytest

from apps.api.config import Settings
from apps.api.db.redis import get_redis
from apps.api.llm.base import ProviderUnavailable
from apps.api.llm.circuit_breaker import CostCeilingExceeded
from apps.api.rag.generator import DECLINE_MESSAGE, DEGRADED_NOTICE, generate
from apps.api.rag.retriever import RetrievedChunk
from apps.api.tests.conftest import FakeProvider

REAL_URL = "https://wordpress.org/plugins/swift-menu-duplicator/#faq"


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content="Theme location assignments are not copied.",
        heading_path="FAQ",
        source_url=REAL_URL,
        score=0.9,
    )


async def _redis_ready() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


pytestmark = pytest.mark.asyncio


async def test_grounded_answer_cites_only_supplied_urls() -> None:
    """The answer keeps supplied citations and strips fabricated ones (FR-GN-1/8)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    chunks = [_chunk()]
    provider = FakeProvider(text=f"Use the settings. See {REAL_URL} and https://evil.com/x.")
    result = await generate(get_redis(), provider, f"q-{uuid.uuid4()}", chunks, model="test-model")

    assert result.citations == [REAL_URL]
    assert "evil.com" not in result.answer
    assert not result.degraded and not result.declined


async def test_identical_second_query_is_cached() -> None:
    """An identical second query is served from cache without a provider call (FR-GN-4)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    chunks = [_chunk()]
    provider = FakeProvider(text=f"Answer with {REAL_URL}.")
    query = f"q-{uuid.uuid4()}"

    first = await generate(get_redis(), provider, query, chunks, model="test-model")
    second = await generate(get_redis(), provider, query, chunks, model="test-model")

    assert provider.calls == 1
    assert second.cached and not first.cached
    assert second.answer == first.answer


async def test_provider_outage_fails_open_with_links(caplog: pytest.LogCaptureFixture) -> None:
    """A provider outage yields a degraded answer with links and logs degraded (FR-GN-6)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    chunks = [_chunk()]
    provider = FakeProvider(error=ProviderUnavailable("down"))

    with caplog.at_level(logging.WARNING):
        result = await generate(
            get_redis(), provider, f"q-{uuid.uuid4()}", chunks, model="test-model"
        )

    assert result.degraded
    assert result.answer == DEGRADED_NOTICE
    assert result.citations == [REAL_URL]
    assert any(getattr(record, "degraded", False) for record in caplog.records)


async def test_empty_retrieval_declines() -> None:
    """Empty retrieval takes the decline path (FR-GN-7)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    result = await generate(get_redis(), FakeProvider(), f"q-{uuid.uuid4()}", [])

    assert result.declined
    assert result.answer == DECLINE_MESSAGE


async def test_oversized_request_refused_by_breaker() -> None:
    """A request over the cost ceiling is refused before the provider call (FR-GN-5)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    chunks = [_chunk()]
    provider = FakeProvider()
    with pytest.raises(CostCeilingExceeded):
        await generate(
            get_redis(),
            provider,
            f"q-{uuid.uuid4()}",
            chunks,
            model="test-model",
            settings=Settings(cost_ceiling_usd_per_request=1e-9),
        )
    assert provider.calls == 0

"""Tests for streaming generation and the SSE query endpoint (FR-DL-3)."""

from __future__ import annotations

import json
import uuid

import pytest
from apps.api.llm.base import ProviderUnavailable, StreamingProvider
from apps.api.rag.generator import DEGRADED_NOTICE, generate_stream
from apps.api.rag.retriever import RetrievedChunk

from tests.conftest import FakeProvider, FakeStreamingProvider

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
    from apps.api.db.redis import get_redis

    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


def test_fake_streaming_provider_satisfies_protocol() -> None:
    """The streaming fake is recognised as a StreamingProvider."""
    assert isinstance(FakeStreamingProvider(), StreamingProvider)
    assert not isinstance(FakeProvider(), StreamingProvider)


async def test_generate_stream_tokens_then_validated_final() -> None:
    """Streaming yields tokens then a citation-validated final event (FR-DL-3/GN-8)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    from apps.api.db.redis import get_redis

    provider = FakeStreamingProvider(text=f"Not copied. See {REAL_URL} and https://evil.com/x.")
    events = [
        event
        async for event in generate_stream(
            get_redis(), provider, f"q-{uuid.uuid4()}", [_chunk()], model="m"
        )
    ]

    tokens = [e for e in events if e.type == "token"]
    finals = [e for e in events if e.type == "final"]
    assert tokens and len(finals) == 1
    final = finals[0]
    assert final.citations == [REAL_URL]
    assert "evil.com" not in (final.answer or "")


async def test_generate_stream_non_streaming_provider_falls_back() -> None:
    """A non-streaming provider still produces token + final events."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    from apps.api.db.redis import get_redis

    provider = FakeProvider(text=f"Answer with {REAL_URL}.")
    events = [
        event
        async for event in generate_stream(
            get_redis(), provider, f"q-{uuid.uuid4()}", [_chunk()], model="m"
        )
    ]
    assert any(e.type == "token" for e in events)
    assert events[-1].type == "final"
    assert events[-1].citations == [REAL_URL]


async def test_generate_stream_degrades_on_provider_failure() -> None:
    """A streaming provider outage yields a degraded final with links (FR-GN-6)."""
    if not await _redis_ready():
        pytest.skip("no Redis reachable")
    from apps.api.db.redis import get_redis

    class _DownStreamer:
        name = "down"

        async def complete(self, request: object) -> object:  # pragma: no cover
            raise ProviderUnavailable("down")

        async def stream(self, request: object) -> object:
            raise ProviderUnavailable("down")
            yield ""  # pragma: no cover

    events = [
        event
        async for event in generate_stream(
            get_redis(), _DownStreamer(), f"q-{uuid.uuid4()}", [_chunk()], model="m"
        )
    ]
    final = events[-1]
    assert final.type == "final" and final.degraded
    assert final.answer == DEGRADED_NOTICE
    assert final.citations == [REAL_URL]


def test_sse_frame_format() -> None:
    """The SSE encoder emits a parseable event/data frame."""
    from apps.api.api.routes_query import _sse

    frame = _sse("token", {"text": "hi"})
    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")
    body = frame.split("data: ", 1)[1].strip()
    assert json.loads(body) == {"text": "hi"}

"""API tests: query, feedback, rate limiting, and admin metrics/auth.

Exercises the HTTP surface the widget depends on against a live DB + Redis, with
the embedding client and LLM provider overridden by deterministic fakes. Skips
when no migrated database is reachable.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from app.api.deps import get_embedding_client, get_provider, get_settings_dep
from app.config import Settings, get_settings
from app.db.engine import dispose_engine, get_engine, get_sessionmaker
from app.db.models import Plugin
from app.db.redis import close_redis, get_redis
from app.ingestion.adapters.base import RawDocument, SourceContext
from app.ingestion.registry import add_source, create_plugin
from app.ingestion.tasks import ingest_source
from app.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tests.conftest import BoWEmbeddingClient, FakeProvider, database_available

SLUG = "swift-menu-duplicator"
REAL_URL = "https://wordpress.org/plugins/swift-menu-duplicator/#faq"


class _StubAdapter:
    """Yields one document so the corpus can answer a known question."""

    handles = ("wporg_faq",)

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        yield RawDocument(
            external_id="faq",
            title="FAQ",
            doc_type="wporg_faq",
            content="Theme location assignments are not copied because they are site specific.",
            content_type="text",
            source_url=REAL_URL,
        )


async def _seed() -> None:
    """Register the plugin and ingest one deterministic document."""
    async with get_sessionmaker()() as session:
        await session.execute(delete(Plugin).where(Plugin.slug == SLUG))
        await session.commit()
    async with get_sessionmaker()() as session:
        plugin = await create_plugin(session, slug=SLUG, name="SMD", wporg_slug=SLUG)
        source = await add_source(session, plugin_id=plugin.id, source_type="wporg_faq")
        await session.commit()
        source_id = source.id
    await ingest_source(
        source_id,
        adapter=_StubAdapter(),
        embedding_client=BoWEmbeddingClient(get_settings().embedding_dimensions),
    )
    # Release engine/Redis built on this loop so the TestClient app builds its own.
    await dispose_engine()
    await close_redis()
    for cached in (get_engine, get_sessionmaker, get_redis):
        cached.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Build an app with fake embedding/provider dependencies and a cited answer."""
    app: FastAPI = create_app()
    app.dependency_overrides[get_embedding_client] = lambda: BoWEmbeddingClient(
        get_settings().embedding_dimensions
    )
    app.dependency_overrides[get_provider] = lambda: FakeProvider(
        text=f"Theme location assignments are not copied. See {REAL_URL}."
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def _ready() -> None:
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")
    await _seed()


async def test_query_returns_cited_answer_and_feedback_roundtrip(
    _ready: None, client: TestClient
) -> None:
    """Query returns a cited answer with a query id; feedback binds to it (FR-DL/FB)."""
    response = client.post(
        "/api/v1/query",
        json={"question": "Does it copy theme location assignments?", "plugin_slug": SLUG},
    )
    assert response.status_code == 200
    body = response.json()
    assert REAL_URL in body["citations"]
    assert any(s["url"] == REAL_URL and s["cited"] for s in body["sources"])
    assert not body["degraded"] and not body["declined"]

    feedback = client.post(
        "/api/v1/feedback", json={"query_id": body["query_id"], "rating": "helpful"}
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "recorded"


async def test_feedback_unknown_query_is_404(_ready: None, client: TestClient) -> None:
    """Feedback for an unknown query id is rejected."""
    response = client.post(
        "/api/v1/feedback", json={"query_id": str(uuid.uuid4()), "rating": "not_helpful"}
    )
    assert response.status_code == 404


async def test_rate_limit_enforced(_ready: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Public endpoints are rate-limited per IP (NFR-SC-2)."""
    monkeypatch.setattr(
        "app.api.deps.get_settings",
        lambda: Settings(rate_limit_max_requests=2, rate_limit_window_seconds=60),
    )
    app = create_app()
    app.dependency_overrides[get_embedding_client] = lambda: BoWEmbeddingClient(8)
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as tc:
        payload = {"question": "hi there", "plugin_slug": SLUG}
        codes = [tc.post("/api/v1/query", json=payload).status_code for _ in range(4)]
    assert 429 in codes


async def test_admin_metrics_requires_bearer(_ready: None, client: TestClient) -> None:
    """Admin metrics reject unauthenticated calls and accept the configured token."""
    assert client.get("/api/v1/admin/metrics").status_code == 401

    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(admin_bearer_token=token)
    with TestClient(app) as tc:
        ok = tc.get("/api/v1/admin/metrics", headers={"Authorization": f"Bearer {token}"})
        bad = tc.get("/api/v1/admin/metrics", headers={"Authorization": "Bearer wrong"})
    assert ok.status_code == 200
    assert "total_queries" in ok.json()
    assert bad.status_code == 401

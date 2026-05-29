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
from app.processing.embedder import EmbeddingUnavailable
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tests.conftest import (
    BoWEmbeddingClient,
    FakeProvider,
    FakeStreamingProvider,
    database_available,
)

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
    # Clear the per-IP rate-limit counter so a fresh budget applies each test.
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match="ratelimit:*")]
    if keys:
        await redis.delete(*keys)
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


async def test_query_without_embeddings_returns_503(_ready: None) -> None:
    """A missing embeddings credential yields a clean 503, not an opaque 500."""

    class _BrokenEmbeddings:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise EmbeddingUnavailable("OpenAI embeddings are not configured")

    app = create_app()
    app.dependency_overrides[get_embedding_client] = _BrokenEmbeddings
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as tc:
        response = tc.post("/api/v1/query", json={"question": "anything?", "plugin_slug": None})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


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
    app.dependency_overrides[get_embedding_client] = lambda: BoWEmbeddingClient(
        get_settings().embedding_dimensions
    )
    app.dependency_overrides[get_provider] = lambda: FakeProvider()
    with TestClient(app) as tc:
        payload = {"question": "hi there", "plugin_slug": SLUG}
        codes = [tc.post("/api/v1/query", json=payload).status_code for _ in range(4)]
    assert 429 in codes


async def test_query_stream_emits_tokens_and_cited_done(_ready: None) -> None:
    """The SSE endpoint streams tokens then a done event with citations (FR-DL-3)."""
    app = create_app()
    app.dependency_overrides[get_embedding_client] = lambda: BoWEmbeddingClient(
        get_settings().embedding_dimensions
    )
    app.dependency_overrides[get_provider] = lambda: FakeStreamingProvider(
        text=f"Theme location assignments are not copied. See {REAL_URL}."
    )
    with TestClient(app) as tc:
        response = tc.post(
            "/api/v1/query/stream",
            json={"question": "Does it copy theme location assignments?", "plugin_slug": SLUG},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = []
    for frame in response.text.split("\n\n"):
        if not frame.strip():
            continue
        name = next(ln[7:] for ln in frame.splitlines() if ln.startswith("event: "))
        data = next(ln[6:] for ln in frame.splitlines() if ln.startswith("data: "))
        events.append((name, __import__("json").loads(data)))

    assert any(name == "token" for name, _ in events)
    done = next(payload for name, payload in events if name == "done")
    assert REAL_URL in done["citations"]
    assert done["query_id"]


async def test_admin_lists_plugins_and_sources(_ready: None) -> None:
    """Admin can list plugins and a plugin's sources (FR-PM-1/2/4)."""
    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(admin_bearer_token=token)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as tc:
        plugins = tc.get("/api/v1/admin/plugins", headers=headers)
        sources = tc.get(f"/api/v1/admin/plugins/{SLUG}/sources", headers=headers)

    assert plugins.status_code == 200
    assert any(p["slug"] == SLUG for p in plugins.json())
    assert sources.status_code == 200
    assert any(s["source_type"] == "wporg_faq" for s in sources.json())


async def test_admin_ingest_all_enqueues_every_source(
    _ready: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ingest-all endpoint enqueues one task per enabled source (FR-IN-6)."""
    from app.ingestion import tasks as tasks_module

    calls: list[str] = []
    monkeypatch.setattr(tasks_module.ingest_source_task, "delay", calls.append)

    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(admin_bearer_token=token)
    with TestClient(app) as tc:
        response = tc.post("/api/v1/admin/ingest", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["plugins"] >= 1
    assert body["enqueued_sources"] == len(calls) >= 1
    assert sum(p["enqueued_sources"] for p in body["by_plugin"]) == body["enqueued_sources"]


async def test_admin_llm_config_override_roundtrip(_ready: None) -> None:
    """Admin can read, override, and reset the active provider/model (FR-GN-3)."""
    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(admin_bearer_token=token)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as tc:
        initial = tc.get("/api/v1/admin/llm", headers=headers)
        assert initial.status_code == 200
        body = initial.json()
        assert body["provider"] == "anthropic"
        assert body["source"] == "env"
        assert {p["name"] for p in body["providers"]} == {"anthropic", "openai", "ollama"}

        set_resp = tc.put(
            "/api/v1/admin/llm",
            headers=headers,
            json={"provider": "ollama", "model": "llama3.1:8b"},
        )
        assert set_resp.status_code == 200
        overridden = set_resp.json()
        assert overridden["provider"] == "ollama"
        assert overridden["model"] == "llama3.1:8b"
        assert overridden["source"] == "override"

        # The override persists across reads.
        assert tc.get("/api/v1/admin/llm", headers=headers).json()["provider"] == "ollama"

        # Omitting the model falls back to the provider's env default.
        defaulted = tc.put(
            "/api/v1/admin/llm", headers=headers, json={"provider": "openai"}
        ).json()
        assert defaulted["provider"] == "openai"
        assert defaulted["model"] == Settings().openai_model

        # Unknown providers are rejected.
        assert (
            tc.put("/api/v1/admin/llm", headers=headers, json={"provider": "nope"}).status_code
            == 422
        )

        reset = tc.delete("/api/v1/admin/llm", headers=headers).json()
        assert reset["source"] == "env"
        assert reset["provider"] == "anthropic"


async def test_admin_embedding_config_guards_dimension_change(_ready: None) -> None:
    """Embedding override applies same-width only; a width change is a 409 (ADR-002)."""
    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: Settings(admin_bearer_token=token)
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as tc:
        body = tc.get("/api/v1/admin/llm", headers=headers).json()
        emb = body["embedding"]
        # Default: OpenAI text-embedding-3-large at 3072 dims.
        assert emb["provider"] == "openai"
        assert emb["dimensions"] == 3072
        names = {p["name"]: p for p in emb["providers"]}
        assert names["ollama"]["dimensions"] == 768
        assert names["ollama"]["applicable"] is False  # 768 != 3072 column
        assert names["openai"]["applicable"] is True

        # Switching to Ollama (768) is rejected: it would change the index width.
        conflict = tc.put(
            "/api/v1/admin/llm/embedding", headers=headers, json={"provider": "ollama"}
        )
        assert conflict.status_code == 409
        assert "re-ingest" in conflict.json()["detail"]

        # A same-width model override is accepted.
        ok = tc.put(
            "/api/v1/admin/llm/embedding",
            headers=headers,
            json={"provider": "openai", "model": "text-embedding-3-small"},
        )
        assert ok.status_code == 200
        assert ok.json()["embedding"]["source"] == "override"
        assert ok.json()["embedding"]["model"] == "text-embedding-3-small"

        reset = tc.delete("/api/v1/admin/llm/embedding", headers=headers).json()
        assert reset["embedding"]["source"] == "env"


async def test_admin_ollama_models_reports_unreachable(_ready: None) -> None:
    """The Ollama models proxy returns reachable=False when the server is down."""
    token = "secret-token"  # noqa: S105 - test-only token
    app = create_app()
    # Point at a closed local port so the request fails fast without any live API.
    app.dependency_overrides[get_settings_dep] = lambda: Settings(
        admin_bearer_token=token,
        ollama_base_url="http://127.0.0.1:9",
        http_timeout_seconds=0.5,
    )
    with TestClient(app) as tc:
        response = tc.get(
            "/api/v1/admin/ollama/models", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["models"] == []


async def test_admin_llm_config_requires_bearer(_ready: None, client: TestClient) -> None:
    """The LLM-config endpoint rejects unauthenticated calls (FR-DL-4)."""
    assert client.get("/api/v1/admin/llm").status_code == 401


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

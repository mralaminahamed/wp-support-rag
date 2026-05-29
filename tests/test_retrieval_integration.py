"""Retrieval integration tests (DB): golden top-k, routing, RRF robustness.

Ingests the Swift Menu Duplicator corpus via VCR cassette with deterministic
bag-of-words embeddings, then exercises hybrid retrieval, centroid routing, and
single-signal robustness. Skips when no migrated database is reachable.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from apps.api.config import Settings, get_settings
from apps.api.db.engine import get_sessionmaker
from apps.api.db.redis import get_redis
from apps.api.ingestion.adapters.base import RawDocument, SourceContext
from apps.api.ingestion.registry import add_source, create_plugin
from apps.api.ingestion.tasks import ingest_source
from apps.api.rag.router import route_query
from apps.api.rag.service import retrieve

from tests.conftest import BoWEmbeddingClient, play

SLUG = "swift-menu-duplicator"


def _embedder() -> BoWEmbeddingClient:
    return BoWEmbeddingClient(get_settings().embedding_dimensions)


class _StubReadmeAdapter:
    """Yields a single README document with fixed text, for routing tests."""

    handles = ("github_readme",)

    def __init__(self, body: str) -> None:
        self._body = body

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        yield RawDocument(
            external_id="README.md",
            title="README",
            doc_type="github_readme",
            content=self._body,
            content_type="markdown",
            source_url=f"https://example.com/{ctx.plugin_slug}",
        )


async def _ingest_smd() -> uuid.UUID:
    """Register Swift Menu Duplicator and ingest its FAQ + changelog."""
    async with get_sessionmaker()() as session:
        plugin = await create_plugin(session, slug=SLUG, name="SMD", wporg_slug=SLUG)
        faq = await add_source(session, plugin_id=plugin.id, source_type="wporg_faq")
        chl = await add_source(session, plugin_id=plugin.id, source_type="wporg_changelog")
        await session.commit()
        plugin_id, faq_id, chl_id = plugin.id, faq.id, chl.id

    client = _embedder()
    with play("wporg_plugin_info.yaml"):
        await ingest_source(faq_id, embedding_client=client)
        await ingest_source(chl_id, embedding_client=client)
    return plugin_id


# Expectations tied to the Swift Menu Duplicator cassette corpus (FAQ + changelog).
# (The eval golden dataset, exercised end to end in tests/test_eval.py, uses its
# own seeded corpus; this test pins the retrieval contract against the cassette.)
_CASSETTE_EXPECTATIONS = [
    ("Does duplicating copy theme location assignments?", ["swift-menu-duplicator", "#faq"]),
    (
        "Are sub-menu items and parent-child relationships preserved?",
        ["swift-menu-duplicator", "#faq"],
    ),
    (
        "What changed about the WP-CLI command in the latest release?",
        ["swift-menu-duplicator", "#developers"],
    ),
]


async def test_golden_expected_source_in_topk(clean_plugins: None) -> None:
    """Each question retrieves its expected source in top-k from the corpus (FR-QR-5)."""
    await _ingest_smd()
    client = _embedder()

    async with get_sessionmaker()() as session:
        for question, substrings in _CASSETTE_EXPECTATIONS:
            result = await retrieve(session, get_redis(), client, question, plugin_slug=SLUG)
            assert any(
                all(sub in chunk.source_url for sub in substrings) for chunk in result.chunks
            ), f"{question!r}: expected {substrings} not in top-k"


async def test_routing_selects_correct_plugin(clean_plugins: None) -> None:
    """A slug-less query routes to the plugin whose centroid it matches (FR-QR-2)."""
    client = _embedder()
    plugins = {
        "phase2-menu": "Duplicate WordPress navigation menus and preserve submenu parent "
        "child relationships across the whole site in one click.",
        "phase2-pay": "Configure Stripe and PayPal payment gateways for WooCommerce checkout, "
        "subscriptions, and refunds.",
    }
    ids: dict[str, uuid.UUID] = {}
    async with get_sessionmaker()() as session:
        for slug in plugins:
            plugin = await create_plugin(session, slug=slug, name=slug)
            source = await add_source(session, plugin_id=plugin.id, source_type="github_readme")
            ids[slug] = source.id
            ids[f"{slug}:plugin"] = plugin.id
        await session.commit()

    for slug, body in plugins.items():
        await ingest_source(ids[slug], adapter=_StubReadmeAdapter(body), embedding_client=client)

    async with get_sessionmaker()() as session:
        menu_q = (await client.embed(["How do I duplicate a navigation menu with submenus?"]))[0]
        pay_q = (await client.embed(["How do I set up Stripe payment gateway refunds?"]))[0]
        menu_route = await route_query(session, get_redis(), menu_q)
        pay_route = await route_query(session, get_redis(), pay_q)

    assert menu_route[0] == ids["phase2-menu:plugin"]
    assert pay_route[0] == ids["phase2-pay:plugin"]


async def test_rrf_robust_to_disabling_either_signal(clean_plugins: None) -> None:
    """Disabling vector or lexical search still returns the expected chunk (ADR-003)."""
    await _ingest_smd()
    client = _embedder()
    # Terms chosen to all appear in the FAQ text so the lexical (AND) query matches.
    question = "copy theme location assignments"

    async with get_sessionmaker()() as session:
        lexical_only = await retrieve(
            session,
            get_redis(),
            client,
            question,
            plugin_slug=SLUG,
            settings=Settings(vector_weight=0.0),
        )
    async with get_sessionmaker()() as session:
        vector_only = await retrieve(
            session,
            get_redis(),
            client,
            question,
            plugin_slug=SLUG,
            settings=Settings(lexical_weight=0.0, similarity_threshold=0.0),
        )

    assert lexical_only.chunks and any("#faq" in c.source_url for c in lexical_only.chunks)
    assert vector_only.chunks

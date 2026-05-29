"""Adapter tests replaying VCR cassettes — no live calls (FR-IN-1/2/3)."""

from __future__ import annotations

from apps.api.ingestion.adapters.base import RawDocument, SourceContext
from apps.api.ingestion.adapters.github import GitHubAdapter
from apps.api.ingestion.adapters.wporg import WporgAdapter

from tests.conftest import play

REPO = "mralaminahamed/swift-menu-duplicator"
SLUG = "swift-menu-duplicator"


async def _collect(adapter: object, ctx: SourceContext, cassette: str) -> list[RawDocument]:
    """Replay a cassette and collect the documents an adapter yields."""
    with play(cassette):
        return [doc async for doc in adapter.fetch(ctx)]  # type: ignore[attr-defined]


async def test_github_readme() -> None:
    """The GitHub adapter decodes the README from the contents API (FR-IN-1)."""
    ctx = SourceContext(plugin_slug=SLUG, source_type="github_readme", github_repo=REPO)
    docs = await _collect(GitHubAdapter(), ctx, "github_readme.yaml")

    assert len(docs) == 1
    assert docs[0].doc_type == "github_readme"
    assert docs[0].content_type == "markdown"
    assert "Swift Menu Duplicator" in docs[0].content


async def test_github_changelog() -> None:
    """The GitHub adapter finds and decodes CHANGELOG.md (FR-IN-1)."""
    ctx = SourceContext(plugin_slug=SLUG, source_type="github_changelog", github_repo=REPO)
    docs = await _collect(GitHubAdapter(), ctx, "github_changelog.yaml")

    assert len(docs) == 1
    assert "Fixed SVN deploy failure." in docs[0].content


async def test_github_issue_qa_pairs_maintainer_answer() -> None:
    """Issues become Q/A docs with the maintainer comment as accepted answer (FR-IN-2)."""
    ctx = SourceContext(
        plugin_slug=SLUG,
        source_type="github_issues",
        github_repo=REPO,
        config={"state": "closed", "labels": ["question", "support"], "per_page": 50},
    )
    docs = await _collect(GitHubAdapter(), ctx, "github_issues.yaml")

    assert len(docs) == 1
    assert "two-pass copy" in docs[0].content
    assert "Accepted answer:" in docs[0].content
    assert docs[0].metadata["has_accepted_answer"] is True


async def test_wporg_faq_and_changelog() -> None:
    """The WordPress.org adapter returns FAQ and changelog sections (FR-IN-3)."""
    faq_ctx = SourceContext(plugin_slug=SLUG, source_type="wporg_faq", wporg_slug=SLUG)
    chl_ctx = SourceContext(plugin_slug=SLUG, source_type="wporg_changelog", wporg_slug=SLUG)

    faq = await _collect(WporgAdapter(), faq_ctx, "wporg_plugin_info.yaml")
    chl = await _collect(WporgAdapter(), chl_ctx, "wporg_plugin_info.yaml")

    assert len(faq) == 1 and faq[0].doc_type == "wporg_faq"
    assert "theme location" in faq[0].content
    assert len(chl) == 1 and chl[0].doc_type == "wporg_changelog"
    assert chl[0].version == "1.0.1"

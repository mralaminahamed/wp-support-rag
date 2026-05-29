"""Tests for heading-aware chunking (FR-PR-2/3)."""

from __future__ import annotations

from apps.api.config import Settings
from apps.api.ingestion.normalize import normalize_markdown
from apps.api.processing.chunker import chunk_document, count_tokens

SMALL = Settings(chunk_target_tokens=20, chunk_max_tokens=30, chunk_overlap_tokens=5)


def _chunk(md: str, settings: Settings) -> list:
    doc = normalize_markdown(md)
    return chunk_document(
        doc,
        plugin_slug="demo",
        doc_type="github_readme",
        source_url="https://example.com/readme",
        version="1.0.0",
        settings=settings,
    )


def test_small_section_is_one_chunk_with_heading_path() -> None:
    """A short section yields one chunk carrying its heading path and metadata."""
    chunks = _chunk("# Guide\n\n## Setup\n\nUpload the plugin.\n", Settings())

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.heading_path == "Guide > Setup"
    assert chunk.embed_text.startswith("Guide > Setup")
    assert "Upload the plugin." in chunk.content
    assert chunk.metadata == {
        "plugin_slug": "demo",
        "doc_type": "github_readme",
        "source_url": "https://example.com/readme",
        "version": "1.0.0",
    }


def test_oversized_section_splits_and_respects_caps() -> None:
    """A large section splits into multiple chunks, each within the hard cap."""
    body = " ".join(f"word{i}" for i in range(80))
    chunks = _chunk(f"# Title\n\n## Big\n\n{body}\n", SMALL)

    assert len(chunks) > 1
    assert all(c.token_count <= SMALL.chunk_max_tokens for c in chunks)
    assert all(c.heading_path == "Title > Big" for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_overlap_carries_across_splits() -> None:
    """Consecutive chunks share trailing/leading tokens from the overlap."""
    body = " ".join(f"token{i}" for i in range(60))
    chunks = _chunk(f"## Section\n\n{body}\n", SMALL)

    assert len(chunks) >= 2
    first_tail = chunks[0].content.split()[-1]
    assert first_tail in chunks[1].content.split()


def test_count_tokens_is_positive_and_monotonic() -> None:
    """The token estimator grows with text length."""
    assert count_tokens("hello world") == 2
    assert count_tokens("a b c d e") > count_tokens("a b")

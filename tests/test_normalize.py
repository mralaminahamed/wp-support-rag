"""Tests for content normalisation and sanitisation."""

from __future__ import annotations

from apps.api.ingestion.normalize import normalize, normalize_html, normalize_markdown


def test_markdown_preserves_heading_path() -> None:
    """Nested ATX headings produce a breadcrumb heading_path."""
    md = "# Title\n\nIntro text.\n\n## Install\n\nRun setup.\n\n### Requirements\n\nPHP 8.1+\n"
    doc = normalize_markdown(md)

    leaf = doc.sections[-1]
    assert leaf.heading_path == ["Title", "Install", "Requirements"]
    assert "PHP 8.1+" in leaf.text
    assert "PHP 8.1+" in doc.text


def test_markdown_strips_links_and_embedded_html() -> None:
    """Link syntax reduces to its label and embedded HTML is stripped (NFR-SC-4)."""
    md = "## Docs\n\nSee [the guide](https://example.com) <script>alert(1)</script> now.\n"
    doc = normalize_markdown(md)

    assert "the guide" in doc.text
    assert "https://example.com" not in doc.text
    assert "alert" not in doc.text
    assert "<script" not in doc.text


def test_html_drops_executable_markup() -> None:
    """HTML normalisation keeps text and discards script bodies (NFR-SC-4)."""
    html = "<h2>FAQ</h2><p>Menus are preserved.</p><script>steal()</script><style>.x{}</style>"
    doc = normalize_html(html)

    assert "FAQ" in doc.text
    assert "Menus are preserved." in doc.text
    assert "steal" not in doc.text
    assert ".x{" not in doc.text
    assert doc.sections[0].heading_path == ["FAQ"]


def test_dispatch_by_content_type() -> None:
    """normalize() dispatches on the declared content type."""
    assert normalize("<p>hi</p>", "html").text == "hi"
    assert normalize("# H\n\nbody", "markdown").sections[0].heading_path == ["H"]
    assert normalize("plain  text", "text").text == "plain text"

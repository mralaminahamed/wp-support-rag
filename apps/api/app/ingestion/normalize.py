"""Content normalisation.

Converts Markdown and HTML source documents into clean plain text while
preserving the heading hierarchy (FR-PR-1), and sanitises away executable markup
so nothing dangerous reaches storage (NFR-SC-4). Output is a
:class:`NormalizedDocument`: the full clean text plus a flat list of
heading-scoped sections that the Phase 3 chunker walks.

Sanitisation is structural: HTML is parsed and only text nodes are kept, with
``<script>``/``<style>`` and similar element bodies discarded entirely, so tags,
attributes, and inline event handlers can never survive into the output.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from pydantic import BaseModel, Field

from app.ingestion.adapters.base import ContentType

# Elements whose entire content is dropped (never user-visible text).
_DROP_ELEMENTS = frozenset(
    {"script", "style", "noscript", "template", "head", "iframe", "object", "embed", "svg"}
)
# Block-level elements that imply a line break around their text.
_BLOCK_ELEMENTS = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "table",
        "section",
        "article",
        "blockquote",
        "pre",
        "hr",
    }
)
_HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MULTISPACE = re.compile(r"[ \t]+")
_MULTINEWLINE = re.compile(r"\n{3,}")


class HeadingSection(BaseModel):
    """A heading-scoped slice of a normalised document.

    Attributes:
        level: Heading depth (1-6); 0 for any preamble before the first heading.
        heading_path: Breadcrumb of ancestor headings ending at this section's
            heading (for example ``["Installation", "Requirements"]``).
        text: Clean body text of the section, excluding the heading line.
    """

    level: int
    heading_path: list[str] = Field(default_factory=list)
    text: str


class NormalizedDocument(BaseModel):
    """Clean text and heading structure for one document.

    Attributes:
        text: The full sanitised plain text, headings included.
        sections: Heading-scoped sections in document order.
    """

    text: str
    sections: list[HeadingSection] = Field(default_factory=list)


class _TextExtractor(HTMLParser):
    """Collect visible text from an HTML fragment, dropping all markup."""

    def __init__(self) -> None:
        """Initialise the extractor with an empty buffer."""
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._depth_in_drop = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Enter a drop element or emit a break for block elements."""
        if tag in _DROP_ELEMENTS:
            self._depth_in_drop += 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Leave a drop element or emit a break for block elements."""
        if tag in _DROP_ELEMENTS and self._depth_in_drop > 0:
            self._depth_in_drop -= 1
        elif tag in _BLOCK_ELEMENTS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Capture text data outside any dropped element."""
        if self._depth_in_drop == 0:
            self._parts.append(data)

    def text(self) -> str:
        """Return the accumulated text.

        Returns:
            str: The concatenated visible text.
        """
        return "".join(self._parts)


def _strip_html(value: str) -> str:
    """Strip all HTML tags from a string, keeping only visible text.

    Args:
        value: A string that may contain HTML markup.

    Returns:
        str: The text content with markup removed.
    """
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def _clean_whitespace(text: str) -> str:
    """Collapse runs of spaces and blank lines, trimming each line.

    Args:
        text: Raw extracted text.

    Returns:
        str: Whitespace-normalised text.
    """
    lines = [_MULTISPACE.sub(" ", line).strip() for line in text.splitlines()]
    joined = "\n".join(lines)
    return _MULTINEWLINE.sub("\n\n", joined).strip()


class _HtmlSectioner(HTMLParser):
    """Parse HTML into heading-scoped sections, dropping executable markup."""

    def __init__(self) -> None:
        """Initialise the sectioner."""
        super().__init__(convert_charrefs=True)
        self._sections: list[tuple[int, str, list[str]]] = []
        self._stack: list[tuple[int, str]] = []
        self._buffer: list[str] = []
        self._level = 0
        self._depth_in_drop = 0
        self._capturing_heading = False
        self._heading_level = 0
        self._heading_parts: list[str] = []

    def _flush(self) -> None:
        """Close the current section, recording it if it has any text."""
        text = _clean_whitespace("".join(self._buffer))
        if text:
            path = [title for _, title in self._stack]
            self._sections.append((self._level, text, path))
        self._buffer = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle an opening tag: headings, drop elements, or block breaks."""
        if tag in _DROP_ELEMENTS:
            self._depth_in_drop += 1
            return
        if self._depth_in_drop:
            return
        if tag in _HEADING_TAGS:
            self._flush()
            self._capturing_heading = True
            self._heading_level = _HEADING_TAGS[tag]
            self._heading_parts = []
        elif tag in _BLOCK_ELEMENTS:
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """Handle a closing tag, finalising headings and drop elements."""
        if tag in _DROP_ELEMENTS:
            if self._depth_in_drop:
                self._depth_in_drop -= 1
            return
        if self._depth_in_drop:
            return
        if tag in _HEADING_TAGS and self._capturing_heading:
            title = _clean_whitespace("".join(self._heading_parts))
            self._capturing_heading = False
            while self._stack and self._stack[-1][0] >= self._heading_level:
                self._stack.pop()
            self._stack.append((self._heading_level, title))
            self._level = self._heading_level
        elif tag in _BLOCK_ELEMENTS:
            self._buffer.append("\n")

    def handle_data(self, data: str) -> None:
        """Capture text into the heading title or the section body."""
        if self._depth_in_drop:
            return
        if self._capturing_heading:
            self._heading_parts.append(data)
        else:
            self._buffer.append(data)

    def sections(self) -> list[HeadingSection]:
        """Return the parsed sections.

        Returns:
            list[HeadingSection]: Sections in document order.
        """
        self._flush()
        return [
            HeadingSection(level=level, heading_path=path, text=text)
            for level, text, path in self._sections
        ]


def normalize_html(content: str) -> NormalizedDocument:
    """Normalise an HTML document to clean text and heading sections.

    Args:
        content: Raw HTML.

    Returns:
        NormalizedDocument: Sanitised text and heading-scoped sections.
    """
    sectioner = _HtmlSectioner()
    sectioner.feed(content)
    sectioner.close()
    sections = sectioner.sections()
    text = _assemble_text(sections)
    return NormalizedDocument(text=text, sections=sections)


def normalize_markdown(content: str) -> NormalizedDocument:
    """Normalise a Markdown document to clean text and heading sections.

    Fenced code blocks are kept as text (their fences removed), link syntax is
    reduced to its visible label, and any embedded HTML is stripped (NFR-SC-4).

    Args:
        content: Raw Markdown.

    Returns:
        NormalizedDocument: Sanitised text and heading-scoped sections.
    """
    sections: list[HeadingSection] = []
    stack: list[tuple[int, str]] = []
    level = 0
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal buffer
        text = _clean_whitespace(_strip_html(_MD_LINK.sub(r"\1", "\n".join(buffer))))
        if text:
            sections.append(
                HeadingSection(level=level, heading_path=[t for _, t in stack], text=text)
            )
        buffer = []

    for raw_line in content.splitlines():
        if raw_line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            match = _ATX_HEADING.match(raw_line)
            if match is not None:
                flush()
                level = len(match.group(1))
                title = _clean_whitespace(_strip_html(_MD_LINK.sub(r"\1", match.group(2))))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                continue
        buffer.append(raw_line)
    flush()

    return NormalizedDocument(text=_assemble_text(sections), sections=sections)


def normalize(content: str, content_type: ContentType) -> NormalizedDocument:
    """Normalise content according to its declared type.

    Args:
        content: Raw document body.
        content_type: One of ``"markdown"``, ``"html"``, or ``"text"``.

    Returns:
        NormalizedDocument: Sanitised text and heading-scoped sections.
    """
    if content_type == "html":
        return normalize_html(content)
    if content_type == "markdown":
        return normalize_markdown(content)
    text = _clean_whitespace(_strip_html(content))
    sections = [HeadingSection(level=0, heading_path=[], text=text)] if text else []
    return NormalizedDocument(text=text, sections=sections)


def _assemble_text(sections: list[HeadingSection]) -> str:
    """Reconstruct full document text from sections, headings included.

    Args:
        sections: The parsed sections.

    Returns:
        str: The full clean text.
    """
    parts: list[str] = []
    for section in sections:
        if section.heading_path:
            parts.append(section.heading_path[-1])
        if section.text:
            parts.append(section.text)
    return "\n\n".join(parts).strip()

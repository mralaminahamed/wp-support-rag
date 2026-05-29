"""Heading-aware chunking.

Walks the normalised heading tree and emits one chunk per leaf section, splitting
oversized sections at paragraph boundaries with a configurable token overlap
(FR-PR-2). Each chunk carries its ``heading_path``, ``token_count``, and the
configured metadata (FR-PR-3); the heading path is prepended to the text that
gets embedded so retrieval is precise on code-heavy docs (§2.3).

Token counting uses a deterministic, offline regex estimator so chunking is
reproducible in CI without fetching tokenizer data. It approximates BPE closely
enough to enforce the configured caps; the embedding model still receives the
exact text.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.config import Settings
from app.ingestion.normalize import NormalizedDocument

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")


class ChunkData(BaseModel):
    """A single chunk produced from a document, ready to embed and persist.

    Attributes:
        chunk_index: Zero-based position of the chunk within its document.
        content: The chunk's clean text (stored verbatim).
        embed_text: The text actually embedded — ``content`` with the heading
            path prepended for retrieval precision.
        heading_path: Heading breadcrumb (for example ``"Installation > Setup"``),
            or ``None`` for preamble before any heading.
        token_count: Estimated token count of ``content``.
        metadata: Chunk metadata (plugin_slug, doc_type, source_url, version) per FR-PR-3.
    """

    chunk_index: int
    content: str
    embed_text: str
    heading_path: str | None
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


def count_tokens(text: str) -> int:
    """Estimate the token count of a string.

    Args:
        text: The text to measure.

    Returns:
        int: Number of word/punctuation tokens (a deterministic BPE approximation).
    """
    return len(_TOKEN_RE.findall(text))


def _overlap_tail(text: str, overlap: int) -> str:
    """Return the trailing text approximating ``overlap`` tokens.

    Args:
        text: The text whose tail to take.
        overlap: Target number of overlap tokens.

    Returns:
        str: The trailing words covering at least ``overlap`` tokens, or ``""``.
    """
    if overlap <= 0:
        return ""
    words = text.split()
    tail: list[str] = []
    for word in reversed(words):
        tail.insert(0, word)
        if count_tokens(" ".join(tail)) >= overlap:
            break
    return " ".join(tail)


def _window_words(text: str, target: int) -> list[str]:
    """Split a paragraph that exceeds ``target`` into word windows.

    Args:
        text: The oversized paragraph.
        target: Soft token target per window.

    Returns:
        list[str]: Windows each near ``target`` tokens.
    """
    windows: list[str] = []
    current: list[str] = []
    for word in text.split():
        current.append(word)
        if count_tokens(" ".join(current)) >= target:
            windows.append(" ".join(current))
            current = []
    if current:
        windows.append(" ".join(current))
    return windows


def _split_section(text: str, settings: Settings) -> list[str]:
    """Split section text into chunk-sized pieces with overlap (FR-PR-2).

    Sections within the hard cap are returned whole; larger sections are packed
    from paragraphs (and word windows for oversized paragraphs) up to the soft
    target, carrying a token overlap across splits.

    Args:
        text: The section's clean text.
        settings: Chunking parameters.

    Returns:
        list[str]: One or more chunk texts, each within the configured cap.
    """
    stripped = text.strip()
    if not stripped:
        return []
    if count_tokens(stripped) <= settings.chunk_max_tokens:
        return [stripped]

    units: list[str] = []
    for paragraph in _PARAGRAPH_SPLIT.split(stripped):
        para = paragraph.strip()
        if not para:
            continue
        if count_tokens(para) > settings.chunk_target_tokens:
            units.extend(_window_words(para, settings.chunk_target_tokens))
        else:
            units.append(para)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}" if current else unit
        if current and count_tokens(candidate) > settings.chunk_target_tokens:
            chunks.append(current)
            tail = _overlap_tail(current, settings.chunk_overlap_tokens)
            current = f"{tail}\n\n{unit}" if tail else unit
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_document(
    document: NormalizedDocument,
    *,
    plugin_slug: str,
    doc_type: str,
    source_url: str,
    version: str | None,
    settings: Settings,
) -> list[ChunkData]:
    """Chunk a normalised document heading-aware (FR-PR-2/3).

    Args:
        document: The normalised document with its heading sections.
        plugin_slug: Owning plugin slug (chunk metadata).
        doc_type: Document type (chunk metadata).
        source_url: Canonical source URL (chunk metadata).
        version: Optional version string (chunk metadata).
        settings: Chunking parameters.

    Returns:
        list[ChunkData]: Ordered chunks with heading-prefixed embed text.
    """
    metadata = {
        "plugin_slug": plugin_slug,
        "doc_type": doc_type,
        "source_url": source_url,
        "version": version,
    }
    chunks: list[ChunkData] = []
    index = 0
    for section in document.sections:
        heading_path = " > ".join(section.heading_path)
        for piece in _split_section(section.text, settings):
            embed_text = f"{heading_path}\n\n{piece}" if heading_path else piece
            chunks.append(
                ChunkData(
                    chunk_index=index,
                    content=piece,
                    embed_text=embed_text,
                    heading_path=heading_path or None,
                    token_count=count_tokens(piece),
                    metadata=metadata,
                )
            )
            index += 1
    return chunks

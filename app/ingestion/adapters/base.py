"""Source adapter contract and transfer models.

Defines the async :class:`SourceAdapter` protocol every documentation source
implements (architecture §2.2), the :class:`RawDocument` it yields, and the
:class:`SourceContext` describing the source to fetch. Adapters are stateless
and async: they fetch raw documents for one configured source and never touch
the database or the embedding pipeline.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

ContentType = Literal["markdown", "html", "text"]
"""How a :class:`RawDocument`'s content should be normalised."""


class SourceFetchError(Exception):
    """Raised on an unrecoverable upstream failure after retries.

    A task catching this marks only its own ingestion run failed, leaving
    sibling sources untouched (FR-IN-7).
    """


class RawDocument(BaseModel):
    """A single logical document fetched from a source, before processing.

    Attributes:
        external_id: Stable upstream identifier (repo path, issue number, thread id).
        title: Optional human-readable title.
        doc_type: Granular document type; equals the originating source type.
        content: Raw document body in the format named by ``content_type``.
        content_type: Format of ``content`` so the normaliser can dispatch.
        source_url: Canonical URL of the document, surfaced in citations.
        version: Optional plugin/document version string.
        metadata: Adapter-specific metadata carried through to the chunk record.
    """

    external_id: str
    title: str | None = None
    doc_type: str
    content: str
    content_type: ContentType
    source_url: str
    version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceContext(BaseModel):
    """Everything an adapter needs to fetch one configured source.

    Built by the ingestion task from the source and plugin rows so adapters stay
    decoupled from the database layer.

    Attributes:
        plugin_slug: Slug of the owning plugin.
        source_type: The source type to fetch (one of the DDL source types).
        github_repo: ``owner/name`` repository, when relevant.
        wporg_slug: WordPress.org plugin slug, when relevant.
        config: Source-specific configuration (labels, paths, state, ...).
        etags: Mutable ETag store for conditional requests (FR-IN-8); the adapter
            reads prior ETags and records fresh ones keyed by URL.
    """

    plugin_slug: str
    source_type: str
    github_repo: str | None = None
    wporg_slug: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    etags: dict[str, str] = Field(default_factory=dict)


@runtime_checkable
class SourceAdapter(Protocol):
    """Contract every documentation source adapter must satisfy.

    Adapters are stateless and async. They fetch raw documents for a single
    configured source and yield normalised :class:`RawDocument` objects. They
    never touch the database or the embedding pipeline directly.
    """

    handles: ClassVar[tuple[str, ...]]
    """The source types this adapter can fetch."""

    def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Fetch all documents for the given source.

        Args:
            ctx: The source to fetch (plugin scope + adapter configuration).

        Returns:
            AsyncIterator[RawDocument]: One item per logical document.

        Raises:
            SourceFetchError: On an unrecoverable upstream failure after retries.
        """
        ...

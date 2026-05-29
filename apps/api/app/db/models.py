"""SQLAlchemy 2.0 declarative models.

Mirrors the schema in ``docs/02-Architecture.md`` §3.2 exactly: plugins, sources,
documents, chunks, ingestion_runs, queries, and feedback, including the
``halfvec(3072)`` embedding column (FR-PR-5), the generated ``tsvector`` lexical
column (FR-PR-6), and every constraint, unique, and index.

The embedding column type and its HNSW operator class are selected from
configuration so the ADR-002 dimensionality fallback (``halfvec(3072)`` vs
``vector(1536)``, NFR-PT-2) is honoured identically by the ORM metadata and the
migration, which both call :func:`embedding_type` and read :data:`HNSW_OPS`.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from pgvector.sqlalchemy import HALFVEC, Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeEngine

from app.config import get_settings

_DIMENSIONS = get_settings().embedding_dimensions
"""Embedding width resolved once from configuration (provider-dependent)."""

HNSW_OPS = (
    "halfvec_cosine_ops" if get_settings().embedding_uses_halfvec else "vector_cosine_ops"
)
"""HNSW operator class matching the configured embedding storage type."""

# Allowed enumerations, kept identical to the DDL CHECK constraints.
PLUGIN_STATUSES = ("active", "paused")
SOURCE_TYPES = (
    "github_readme",
    "github_changelog",
    "github_docs",
    "github_issues",
    "wporg_faq",
    "wporg_changelog",
    "wporg_support",
)
RUN_STATUSES = ("running", "succeeded", "failed")
FEEDBACK_RATINGS = ("helpful", "not_helpful")


def embedding_type() -> TypeEngine[Any]:
    """Return the SQLAlchemy column type for chunk embeddings.

    The choice follows ADR-002: full-fidelity ``halfvec`` by default (3072 for
    OpenAI, the model's native width for Ollama), or ``vector(1536)`` when
    configuration selects the pgvector < 0.7.0 fallback (NFR-PT-2). The migration
    calls this so column and index agree on the type.

    Returns:
        TypeEngine[Any]: ``HALFVEC(dim)`` or ``Vector(1536)`` per configuration.
    """
    if get_settings().embedding_uses_halfvec:
        return cast("TypeEngine[Any]", HALFVEC(_DIMENSIONS))
    return cast("TypeEngine[Any]", Vector(_DIMENSIONS))


def _uuid_pk() -> Mapped[uuid.UUID]:
    """Return a UUID primary-key column defaulting to ``gen_random_uuid()``.

    Returns:
        Mapped[uuid.UUID]: The configured primary-key column.
    """
    return mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Mapped[datetime]:
    """Return a non-null ``timestamptz`` column defaulting to ``now()``.

    Returns:
        Mapped[datetime]: The creation-timestamp column.
    """
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Base(DeclarativeBase):
    """Declarative base carrying the shared metadata for all models."""


class Plugin(Base):
    """A registered WordPress plugin and its retrieval scope (FR-PM-1).

    Attributes:
        id: Surrogate primary key.
        slug: Unique operator-facing identifier used to scope retrieval.
        name: Human-readable display name.
        wporg_slug: Optional WordPress.org plugin slug.
        github_repo: Optional ``owner/name`` GitHub repository.
        status: Lifecycle status, one of :data:`PLUGIN_STATUSES`.
        created_at: Row creation timestamp.
        updated_at: Row last-update timestamp.
        sources: Sources attached to this plugin.
        chunks: Chunks denormalised against this plugin for fast filtering.
    """

    __tablename__ = "plugins"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused')",
            name="plugins_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    wporg_slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_repo: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    sources: Mapped[list[Source]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[Chunk]] = relationship(back_populates="plugin")


class Source(Base):
    """A typed documentation source attached to a plugin (FR-PM-2/3/4).

    Attributes:
        id: Surrogate primary key.
        plugin_id: Owning plugin.
        source_type: Source kind, one of :data:`SOURCE_TYPES`.
        config: Adapter-specific configuration as JSONB.
        enabled: Whether ingestion runs for this source (FR-PM-3).
        last_ingested_at: Timestamp of the last successful ingestion (FR-PM-4).
        plugin: The owning plugin.
        documents: Documents fetched from this source.
        ingestion_runs: Ingestion run history for this source.
    """

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ("
            "'github_readme','github_changelog','github_docs',"
            "'github_issues','wporg_faq','wporg_changelog','wporg_support')",
            name="sources_source_type_check",
        ),
        UniqueConstraint("plugin_id", "source_type", name="sources_plugin_id_source_type_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    last_ingested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    plugin: Mapped[Plugin] = relationship(back_populates="sources")
    documents: Mapped[list[Document]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Document(Base):
    """A single logical document fetched from a source.

    Attributes:
        id: Surrogate primary key.
        source_id: Owning source.
        plugin_id: Denormalised owning plugin.
        external_id: Stable upstream id (repo path, issue number, thread id).
        title: Optional document title.
        doc_type: Granular document type mirroring the source type.
        content_hash: Hash of normalised content for change detection (FR-PR-7).
        source_url: Canonical source URL, surfaced in citations.
        version: Optional plugin/document version string.
        fetched_at: When the document was fetched.
        source: The owning source.
        plugin: The owning plugin.
        chunks: Chunks derived from this document.
    """

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="documents_source_id_external_id_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = _created_at()

    source: Mapped[Source] = relationship(back_populates="documents")
    plugin: Mapped[Plugin] = relationship()
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """An embedded, lexically indexed slice of a document (FR-PR-3/5/6).

    Attributes:
        id: Surrogate primary key.
        document_id: Owning document.
        plugin_id: Denormalised owning plugin for fast scoped filtering.
        chunk_index: Position of the chunk within its document.
        content: The chunk text.
        content_tsv: Generated lexical vector over ``content`` (FR-PR-6).
        heading_path: Heading breadcrumb prepended to embedded text.
        token_count: Token count of the chunk.
        embedding: Dense embedding vector (FR-PR-5; type per ADR-002).
        meta: Arbitrary chunk metadata as JSONB (mapped from column ``metadata``).
        created_at: Row creation timestamp.
        document: The owning document.
        plugin: The owning plugin.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="chunks_document_id_chunk_index_key"),
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": HNSW_OPS},
        ),
        Index("chunks_content_tsv_gin", "content_tsv", postgresql_using="gin"),
        Index("chunks_plugin_id", "plugin_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    plugin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=False,
    )
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(embedding_type(), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[Document] = relationship(back_populates="chunks")
    plugin: Mapped[Plugin] = relationship(back_populates="chunks")


class IngestionRun(Base):
    """A record of a single ingestion attempt for one source (FR-PM-4, FR-IN-7).

    Attributes:
        id: Surrogate primary key.
        source_id: The source that was ingested.
        status: Run status, one of :data:`RUN_STATUSES`.
        started_at: When the run started.
        finished_at: When the run finished, if it has.
        documents_processed: Count of documents handled in the run.
        chunks_created: Count of chunks produced in the run.
        error: Failure detail when ``status`` is ``failed``.
        source: The ingested source.
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')",
            name="ingestion_runs_status_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    documents_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    chunks_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[Source] = relationship(back_populates="ingestion_runs")


class Query(Base):
    """A logged query and its observability record (architecture §4.3).

    Attributes:
        id: Surrogate primary key.
        plugin_id: Resolved plugin, nullable and set null on plugin deletion.
        query_text: The user question.
        retrieved_chunk_ids: Ordered ids of chunks supplied to generation.
        response_text: The generated answer, if any.
        provider: Provider that served the answer.
        prompt_version: Active prompt version used.
        tokens_in: Prompt token count.
        tokens_out: Completion token count.
        cost_usd: Estimated request cost.
        cached: Whether the answer was served from cache.
        degraded: Whether fail-open degraded mode was used (FR-GN-6).
        latency_ms: End-to-end latency in milliseconds.
        ip_hash: Hashed/truncated caller IP, for rate limiting only (NFR-SC-2).
        created_at: Row creation timestamp.
        plugin: The resolved plugin, if still present.
        feedback: Feedback entries bound to this query.
    """

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    plugin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plugins.id", ondelete="SET NULL"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    cached: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    degraded: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    plugin: Mapped[Plugin | None] = relationship()
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="query", cascade="all, delete-orphan"
    )


class Feedback(Base):
    """User feedback bound to a logged query (FR-FB-*).

    Attributes:
        id: Surrogate primary key.
        query_id: The query this feedback concerns.
        rating: Feedback rating, one of :data:`FEEDBACK_RATINGS`.
        comment: Optional free-text comment.
        created_at: Row creation timestamp.
        query: The query this feedback concerns.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "rating IN ('helpful','not_helpful')",
            name="feedback_rating_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()

    query: Mapped[Query] = relationship(back_populates="feedback")

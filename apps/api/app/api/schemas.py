"""API request/response models (Pydantic v2).

Defines the public query and feedback contracts consumed by the widget plus the
admin metrics and ingestion-trigger payloads. User-supplied text is length-bounded
and treated as untrusted (NFR-SC-3).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """A public query request (FR-QR-1, FR-DL-1).

    Attributes:
        question: The free-text question (length-bounded, untrusted).
        plugin_slug: Optional plugin filter; routing runs when omitted.
    """

    question: str = Field(min_length=1, max_length=2000)
    plugin_slug: str | None = Field(default=None, max_length=200)


class SourceRef(BaseModel):
    """A cited or retrieved source for display in the widget.

    Attributes:
        url: Canonical source URL.
        heading_path: Heading breadcrumb of the chunk, if any.
        cited: Whether the answer cited this source.
    """

    url: str
    heading_path: str | None = None
    cited: bool = False


class QueryResponse(BaseModel):
    """The answer returned to the widget (FR-QR-5, FR-GN-6/7).

    Attributes:
        query_id: Id of the persisted query record (bind feedback to it).
        answer: The grounded answer, or a decline/degraded notice.
        citations: Source URLs cited in the answer.
        sources: Retrieved sources with links (shown especially when degraded).
        cached: Whether the answer came from cache.
        degraded: Whether fail-open degraded mode was used.
        declined: Whether the decline path was taken.
        plugin_slug: The plugin filter that was applied, if any.
        latency_ms: End-to-end latency in milliseconds.
    """

    query_id: uuid.UUID
    answer: str
    citations: list[str]
    sources: list[SourceRef]
    cached: bool
    degraded: bool
    declined: bool
    plugin_slug: str | None
    latency_ms: int


class FeedbackRequest(BaseModel):
    """User feedback bound to a query (FR-FB-2).

    Attributes:
        query_id: The query this feedback concerns.
        rating: ``helpful`` or ``not_helpful``.
        comment: Optional free-text comment (bounded).
    """

    query_id: uuid.UUID
    rating: Literal["helpful", "not_helpful"]
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    """Acknowledgement of recorded feedback.

    Attributes:
        status: Always ``"recorded"`` on success.
    """

    status: str = "recorded"


class MetricsResponse(BaseModel):
    """Aggregate operational metrics (FR-FB-3).

    Attributes:
        total_queries: Number of logged queries.
        deflection_rate: Fraction answered without degradation.
        helpful_rate: Fraction of feedback marked helpful.
        cache_hit_rate: Fraction of queries served from cache.
        degraded_rate: Fraction of queries served in degraded mode.
        mean_cost_usd: Mean estimated cost per query.
        p95_latency_ms: 95th-percentile end-to-end latency.
    """

    total_queries: int
    deflection_rate: float
    helpful_rate: float
    cache_hit_rate: float
    degraded_rate: float
    mean_cost_usd: float
    p95_latency_ms: int


class PluginRegistration(BaseModel):
    """Admin plugin registration payload (FR-PM-1/2).

    Attributes:
        slug: Unique plugin slug.
        name: Display name.
        wporg_slug: Optional WordPress.org slug.
        github_repo: Optional ``owner/name`` repository.
        source_types: Source types to attach.
    """

    slug: str = Field(max_length=200)
    name: str = Field(max_length=400)
    wporg_slug: str | None = None
    github_repo: str | None = None
    source_types: list[str] = Field(default_factory=list)


class PluginSummary(BaseModel):
    """A registered plugin for admin listing (FR-PM-1).

    Attributes:
        slug: Plugin slug.
        name: Display name.
        status: Lifecycle status.
        wporg_slug: WordPress.org slug, if set.
        github_repo: GitHub repository, if set.
        source_count: Number of attached sources.
    """

    slug: str
    name: str
    status: str
    wporg_slug: str | None
    github_repo: str | None
    source_count: int


class SourceSummary(BaseModel):
    """A plugin source for admin listing (FR-PM-2/4).

    Attributes:
        source_type: The typed source kind.
        enabled: Whether the source is enabled.
        last_ingested_at: ISO timestamp of the last ingestion, if any.
    """

    source_type: str
    enabled: bool
    last_ingested_at: str | None


class IngestTriggerResponse(BaseModel):
    """Result of triggering ingestion for a plugin (FR-IN-6).

    Attributes:
        plugin_slug: The plugin whose sources were enqueued.
        enqueued_sources: Number of enabled sources dispatched.
    """

    plugin_slug: str
    enqueued_sources: int


class IngestAllResponse(BaseModel):
    """Result of triggering ingestion for every plugin (FR-IN-6).

    Attributes:
        plugins: Number of plugins processed.
        enqueued_sources: Total enabled sources dispatched across all plugins.
        by_plugin: Per-plugin enqueue counts.
    """

    plugins: int
    enqueued_sources: int
    by_plugin: list[IngestTriggerResponse]


class LLMProviderInfo(BaseModel):
    """A selectable generation provider and its env-default model (FR-GN-3).

    Attributes:
        name: The provider name.
        default_model: The model id configured for this provider in the env file.
        configured: Whether the provider has the credentials/endpoint it needs.
    """

    name: str
    default_model: str
    configured: bool


class EmbeddingProviderInfo(BaseModel):
    """A selectable embedding provider and its width (FR-GN-3, ADR-002).

    Attributes:
        name: The provider name.
        default_model: The embedding model configured for this provider.
        dimensions: The vector width that model produces.
        configured: Whether the provider has the credentials/endpoint it needs.
        applicable: Whether it can be applied at runtime (same width as the live
            DB column); a different width needs a migration and re-embed.
    """

    name: str
    default_model: str
    dimensions: int
    configured: bool
    applicable: bool


class EmbeddingConfig(BaseModel):
    """The active embedding provider/model and the available choices (ADR-002).

    Attributes:
        provider: The active embedding provider name.
        model: The active embedding model id.
        dimensions: The live vector width (bound to the DB column).
        source: ``"override"`` if set from the admin UI, else ``"env"``.
        providers: All embedding providers with their widths and applicability.
    """

    provider: str
    model: str
    dimensions: int
    source: str
    providers: list[EmbeddingProviderInfo]


class EmbeddingConfigUpdate(BaseModel):
    """Request to override the active embedding provider/model (ADR-002).

    Attributes:
        provider: The embedding provider to activate.
        model: Optional model id; falls back to the provider's configured model.
    """

    provider: str
    model: str | None = None


class LLMConfigResponse(BaseModel):
    """The active generation + embedding config and the available choices (FR-GN-3).

    Attributes:
        provider: The active generation provider name.
        model: The active generation model id.
        source: ``"override"`` if set from the admin UI, else ``"env"``.
        default_provider: The generation provider configured in the env file.
        providers: All selectable generation providers with their env-default models.
        embedding: The active embedding configuration and choices.
    """

    provider: str
    model: str
    source: str
    default_provider: str
    providers: list[LLMProviderInfo]
    embedding: EmbeddingConfig


class LLMConfigUpdate(BaseModel):
    """Request to override the active generation provider/model (FR-GN-3).

    Attributes:
        provider: The provider to activate.
        model: Optional model id; falls back to the provider's env default.
    """

    provider: str
    model: str | None = None

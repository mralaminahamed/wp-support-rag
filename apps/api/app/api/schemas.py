"""API request/response models (Pydantic v2).

Defines the public query and feedback contracts consumed by the widget plus the
admin metrics and ingestion-trigger payloads. User-supplied text is length-bounded
and treated as untrusted (NFR-SC-3).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
        provider: Generation provider that produced the answer.
        model: Generation model id that produced the answer.
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
    provider: str
    model: str


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
        chunk_count: Total chunks indexed for this plugin.
    """

    slug: str
    name: str
    status: str
    wporg_slug: str | None
    github_repo: str | None
    source_count: int
    chunk_count: int


class SourceSummary(BaseModel):
    """A plugin source for admin listing (FR-PM-2/4).

    Attributes:
        source_id: The source UUID.
        source_type: The typed source kind.
        enabled: Whether the source is enabled.
        last_ingested_at: ISO timestamp of the last ingestion, if any.
        chunk_count: Total chunks currently in the DB for this source.
        run_status: Status of the most recent ingestion run, if any.
        run_chunks: Chunks created in the most recent run, if any.
        run_docs: Documents processed in the most recent run, if any.
        run_error: Error message from the most recent failed run, if any.
        run_finished_at: ISO timestamp when the most recent run finished, if any.
    """

    source_id: str
    source_type: str
    name: str
    enabled: bool
    last_ingested_at: str | None
    chunk_count: int = 0
    run_status: str | None = None
    run_chunks: int | None = None
    run_docs: int | None = None
    run_error: str | None = None
    run_finished_at: str | None = None


class PluginUpdate(BaseModel):
    """Partial update for a plugin (name, slugs, status).

    Attributes:
        name: New display name.
        wporg_slug: WordPress.org slug override (null clears it).
        github_repo: GitHub repo override (null clears it).
        status: Lifecycle status — ``active`` or ``paused``.
    """

    name: str | None = Field(default=None, max_length=400)
    wporg_slug: str | None = None
    github_repo: str | None = None
    status: Literal["active", "paused"] | None = None


class PatchSourceRequest(BaseModel):
    """Partial update for a source (enable/disable).

    Attributes:
        enabled: New enabled state.
    """

    enabled: bool


class AddSourceRequest(BaseModel):
    """Add a source to an existing plugin."""

    source_type: str
    name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class PatchConfigRequest(BaseModel):
    """Update the config of an existing source."""

    config: dict[str, Any]


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


class RecentQuery(BaseModel):
    """A logged query for the admin activity feed (FR-FB-1/3).

    Attributes:
        id: The query id.
        query_text: The user question.
        plugin_slug: Resolved plugin slug, if any.
        provider: Provider that served the answer.
        cached: Whether the answer came from cache.
        degraded: Whether fail-open degraded mode was used.
        latency_ms: End-to-end latency in milliseconds, if recorded.
        created_at: ISO timestamp of when the query was logged.
        thread_id: Conversation thread that contains this query, if any.
    """

    id: uuid.UUID
    query_text: str
    plugin_slug: str | None
    provider: str | None
    cached: bool
    degraded: bool
    latency_ms: int | None
    created_at: str
    thread_id: uuid.UUID | None = None


class OllamaModelsResponse(BaseModel):
    """Models available on the configured Ollama server (FR-GN-3).

    Attributes:
        reachable: Whether the Ollama server responded.
        base_url: The Ollama base URL that was queried.
        models: Model names available for selection (generation or embedding).
    """

    reachable: bool
    base_url: str
    models: list[str]


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


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Credentials for POST /api/v1/auth/login.

    Attributes:
        email: User email address.
        password: Plain-text password (transmitted over TLS only).
    """

    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    """Credentials for POST /api/v1/auth/register (open registration).

    Attributes:
        email: Desired email address.
        password: Desired password (min 8 chars).
    """

    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=1024)


class AcceptInviteRequest(BaseModel):
    """Body for POST /api/v1/auth/accept-invite.

    Attributes:
        token: Raw invite token UUID from the invite URL.
        password: Desired password (min 8 chars).
    """

    token: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=8, max_length=1024)


class AuthUserResponse(BaseModel):
    """User identity returned after login / register / me.

    Attributes:
        id: User UUID.
        email: User email.
        roles: Role names held by the user.
        permissions: Effective permission strings.
        is_active: Whether the account is active.
        created_at: ISO creation timestamp.
    """

    id: uuid.UUID
    email: str
    roles: list[str]
    permissions: list[str]
    is_active: bool
    created_at: str


class UserListItem(BaseModel):
    """Summary row for GET /api/v1/admin/users.

    Attributes:
        id: User UUID.
        email: User email.
        roles: Role names.
        is_active: Account status.
        created_at: ISO creation timestamp.
    """

    id: uuid.UUID
    email: str
    roles: list[str]
    is_active: bool
    created_at: str


class CreateUserRequest(BaseModel):
    """Body for POST /api/v1/admin/users.

    Attributes:
        email: New user email.
        password: Initial password (min 8 chars).
        role_ids: UUIDs of roles to assign.
    """

    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class PatchUserRequest(BaseModel):
    """Body for PATCH /api/v1/admin/users/{user_id}.

    Attributes:
        is_active: Set account active/inactive.
        role_ids: Replace the user's roles with this list.
    """

    is_active: bool | None = None
    role_ids: list[uuid.UUID] | None = None


class InviteRequest(BaseModel):
    """Body for POST /api/v1/admin/users/invite.

    Attributes:
        email: Invitee email address.
        role_id: Role assigned to the new account on acceptance.
    """

    email: str = Field(max_length=320)
    role_id: uuid.UUID


class InviteResponse(BaseModel):
    """Response from POST /api/v1/admin/users/invite.

    Attributes:
        token: Raw invite token (caller must transmit to invitee).
        invite_url: Full URL if WPRAG_ADMIN_URL is configured, else None.
    """

    token: str
    invite_url: str | None = None


class InviteSummary(BaseModel):
    """An invite token for admin listing.

    Attributes:
        id: Invite UUID.
        email: Invitee email.
        role_name: Role name assigned on acceptance, or None.
        status: pending | expired | accepted.
        expires_at: ISO expiry timestamp.
        used_at: ISO acceptance timestamp, or None.
    """

    id: str
    email: str
    role_name: str | None
    status: Literal["pending", "expired", "accepted"]
    created_at: str
    expires_at: str
    used_at: str | None


class RoleSummary(BaseModel):
    """A role with its permission list for admin listing.

    Attributes:
        id: Role UUID.
        name: Role name.
        description: Human-readable description.
        is_system: Whether this is a built-in undeletable role.
        permissions: Permission strings granted to this role.
    """

    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]


class CreateRoleRequest(BaseModel):
    """Body for POST /api/v1/admin/roles.

    Attributes:
        name: Unique role name.
        description: Optional description.
        permissions: Permission strings to grant.
    """

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class PatchRoleRequest(BaseModel):
    """Body for PATCH /api/v1/admin/roles/{role_id}.

    Attributes:
        description: Updated description (system roles: allowed).
        permissions: Replacement permission list.
    """

    description: str | None = None
    permissions: list[str] | None = None


class ForgotPasswordRequest(BaseModel):
    """Body for POST /api/v1/auth/forgot-password.

    Attributes:
        email: The account email address to send the reset link to.
    """

    email: str = Field(max_length=320)


class ResetPasswordRequest(BaseModel):
    """Body for POST /api/v1/auth/reset-password.

    Attributes:
        token: Raw reset token from the email link.
        password: New plain-text password (min 8 chars).
    """

    token: str
    password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    """Body for PATCH /api/v1/auth/me/password.

    Attributes:
        current_password: The user's current password for verification.
        new_password: Replacement password (min 8 chars).
    """

    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class SetupStatusResponse(BaseModel):
    """Response for setup status and completion endpoints.

    Attributes:
        complete: Whether the first-run setup wizard has been completed.
    """

    complete: bool


class NetworkConfigResponse(BaseModel):
    """Stored network / admin URL config.

    Attributes:
        admin_url: The public base URL of this admin console (used for server-generated links).
    """

    admin_url: str | None


class NetworkConfigRequest(BaseModel):
    """Set the admin URL during setup.

    Attributes:
        admin_url: The public base URL (e.g. http://192.168.1.10 for LAN access).
    """

    admin_url: str = Field(max_length=500)


class CreateAdminRequest(BaseModel):
    """Create the first super-admin account during setup.

    Attributes:
        email: Admin email address.
        password: Plaintext password (hashed server-side).
    """

    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)


class CreateAdminResponse(BaseModel):
    """Confirmation of admin account creation.

    Attributes:
        id: New user UUID.
        email: Admin email address.
    """

    id: str
    email: str


# ---------------------------------------------------------------------------
# Conversation thread schemas
# ---------------------------------------------------------------------------


class ThreadSummary(BaseModel):
    """A conversation thread for sidebar listing.

    Attributes:
        id: Thread UUID.
        title: Short title (first question, truncated).
        plugin_slug: Plugin filter active for this thread, if any.
        created_at: ISO creation timestamp.
        updated_at: ISO last-activity timestamp.
    """

    id: uuid.UUID
    title: str
    plugin_slug: str | None
    created_at: str
    updated_at: str
    owner_email: str | None = None


class ThreadMessageItem(BaseModel):
    """A single message within a thread.

    Attributes:
        id: Message UUID.
        role: ``"user"`` or ``"assistant"``.
        content: Message text.
        query_id: Linked query UUID for assistant messages, if any.
        meta: Full QueryResponse payload for assistant messages, if stored.
        created_at: ISO creation timestamp.
    """

    id: uuid.UUID
    role: str
    content: str
    query_id: uuid.UUID | None
    meta: dict | None
    created_at: str


class CreateThreadRequest(BaseModel):
    """Create a new conversation thread.

    Attributes:
        title: Short title (caller should truncate to ~80 chars).
        plugin_slug: Optional plugin filter active for this thread.
    """

    title: str = Field(min_length=1, max_length=200)
    plugin_slug: str | None = Field(default=None, max_length=200)


class AppendMessageItem(BaseModel):
    """One message to append in a batch.

    Attributes:
        role: ``"user"`` or ``"assistant"``.
        content: Message text.
        query_id: Linked query UUID for assistant messages.
        meta: Full QueryResponse JSON for assistant messages.
    """

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=0, max_length=100_000)
    query_id: uuid.UUID | None = None
    meta: dict | None = None


class AppendMessagesRequest(BaseModel):
    """Batch-append messages to a thread (one user + one assistant per turn).

    Attributes:
        messages: Ordered list of messages to append.
    """

    messages: list[AppendMessageItem] = Field(min_length=1, max_length=10)


class AdapterPluginSummary(BaseModel):
    """API response model for an installed adapter plugin.

    Attributes:
        slug: Unique plugin identifier.
        display_name: Human-readable plugin name.
        version: Semantic version string, or None if not available.
        source: Origin of the plugin (builtin, entrypoint, or file-based).
        handles: List of document types this plugin can process.
        status: Current plugin state (loaded, error, or disabled).
        error: Error message if status is 'error', else None.
        installed_at: ISO timestamp when the plugin was installed/discovered.
    """

    slug: str
    display_name: str
    version: str | None
    source: Literal["builtin", "entrypoint", "file"]
    handles: list[str]
    status: Literal["loaded", "error", "disabled"]
    error: str | None
    installed_at: datetime

    model_config = ConfigDict(from_attributes=True)

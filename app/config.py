"""Application configuration.

Single source of truth for every runtime tunable in the service. Values are read
from the environment (prefix ``WPRAG_``) and an optional ``.env`` file, validated
once on load by Pydantic, and consumed everywhere via :func:`get_settings`.

No behavioural constant may be hard-coded elsewhere in the codebase (NFR-MN-4);
providers, prompt resolution, chunking, retrieval weights, cache TTLs, the cost
ceiling, and the rate-limit window all originate here.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "openai", "ollama"]
"""The set of generation providers the factory can resolve (architecture §2.5)."""

DimensionalityMode = Literal["halfvec_3072", "vector_1536"]
"""Embedding storage mode. ``halfvec_3072`` is the default per ADR-002; ``vector_1536``
is the pgvector < 0.7.0 fallback selected by configuration (NFR-PT-2)."""

Environment = Literal["development", "staging", "production"]
"""Deployment environment, used to gate environment-specific behaviour."""


class Settings(BaseSettings):
    """Validated, environment-driven application settings.

    Every field maps to a configuration key named in ``docs/02-Architecture.md`` §4.1.
    Defaults reflect the documented defaults; secrets carry no default and must be
    supplied by the environment. Validation runs on instantiation so a misconfigured
    deployment fails fast at startup rather than at first use.

    Attributes:
        app_name: Human-readable service name surfaced in logs and ``/health``.
        environment: Active deployment environment.
        log_level: Root log level for the structured logger.
        database_dsn: Async SQLAlchemy DSN for PostgreSQL + pgvector.
        redis_dsn: Redis DSN used for the response cache, Celery broker, and rate limiter.
        anthropic_api_key: Claude provider credential (optional if unused).
        openai_api_key: OpenAI credential, required for embeddings and the OpenAI provider.
        ollama_base_url: Base URL of a local Ollama server.
        default_provider: Provider the factory resolves when none is requested.
        github_token: Optional GitHub token raising the REST rate limit (NFR-SC-1).
        github_api_url: Base URL of the GitHub REST API.
        wporg_api_url: Base URL of the WordPress.org API host.
        wporg_site_url: Base URL of the WordPress.org site (support forums).
        http_timeout_seconds: Per-request timeout for outbound ingestion HTTP calls.
        http_max_retries: Bounded retry count for transient ingestion failures (FR-IN-8).
        http_user_agent: User-Agent sent on all outbound ingestion requests.
        ingest_polite_delay_seconds: Delay between polite HTML retrievals (FR-IN-4).
        embed_model: Embedding model identifier.
        embed_batch_size: Maximum texts per embedding call (hard cap 100).
        dimensionality_mode: Embedding storage/dimension mode (ADR-002).
        chunk_target_tokens: Soft per-chunk token target.
        chunk_max_tokens: Hard per-chunk token cap before a forced split.
        chunk_overlap_tokens: Token overlap carried across paragraph splits.
        rrf_k: Reciprocal Rank Fusion constant (architecture §2.4).
        retrieval_top_n: Per-list candidate depth before fusion.
        retrieval_top_k: Final number of chunks passed to generation.
        ef_search: HNSW query-time search breadth (recall/latency trade-off).
        vector_weight: Relative weight of the vector list during fusion.
        lexical_weight: Relative weight of the lexical list during fusion.
        similarity_threshold: Minimum vector similarity for a vector-only chunk to survive.
        rerank_enabled: Whether the optional rerank stage runs.
        route_max_plugins: Max plugins a slug-less query routes to (ADR-004).
        response_cache_ttl_seconds: Default TTL for cached answers.
        centroid_cache_ttl_seconds: TTL for cached per-plugin centroid embeddings.
        cost_ceiling_usd_per_request: Per-request projected-cost ceiling (FR-GN-5).
        rate_limit_max_requests: Allowed public requests per window per hashed IP.
        rate_limit_window_seconds: Length of the rate-limit window.
        admin_bearer_token: Bearer token guarding admin endpoints (NFR-SC-2).
        cors_origins: Origins permitted to call the public query API from the widget.
    """

    model_config = SettingsConfigDict(
        env_prefix="WPRAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Service ---
    app_name: str = "wp-support-rag"
    environment: Environment = "development"
    log_level: str = "INFO"

    # --- Datastores (architecture §1.1, §4.1) ---
    database_dsn: str = "postgresql+asyncpg://wprag:wprag@localhost:5432/wprag"
    redis_dsn: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))

    # --- Provider credentials and selection (§2.5) ---
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
    default_provider: ProviderName = "anthropic"

    # --- Ingestion sources (§2.2, FR-IN-*) ---
    github_token: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    wporg_api_url: str = "https://api.wordpress.org"
    wporg_site_url: str = "https://wordpress.org"
    http_timeout_seconds: float = Field(default=30.0, gt=0.0)
    http_max_retries: int = Field(default=4, ge=0)
    http_user_agent: str = "wp-support-rag/0.1 (+https://github.com/mralaminahamed)"
    ingest_polite_delay_seconds: float = Field(default=1.0, ge=0.0)

    # --- Embedding (§2.3, ADR-002) ---
    embed_model: str = "text-embedding-3-large"
    embed_batch_size: int = Field(default=100, ge=1, le=100)
    dimensionality_mode: DimensionalityMode = "halfvec_3072"

    # --- Chunking (§2.3) ---
    chunk_target_tokens: int = Field(default=512, ge=1)
    chunk_max_tokens: int = Field(default=768, ge=1)
    chunk_overlap_tokens: int = Field(default=64, ge=0)

    # --- Retrieval (§2.4) ---
    rrf_k: int = Field(default=60, ge=1)
    retrieval_top_n: int = Field(default=40, ge=1)
    retrieval_top_k: int = Field(default=8, ge=1)
    ef_search: int = Field(default=80, ge=1)
    vector_weight: float = Field(default=1.0, ge=0.0)
    lexical_weight: float = Field(default=1.0, ge=0.0)
    similarity_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    rerank_enabled: bool = False
    route_max_plugins: int = Field(default=2, ge=1)

    # --- Caching (§2.5) ---
    response_cache_ttl_seconds: int = Field(default=86_400, ge=0)
    centroid_cache_ttl_seconds: int = Field(default=604_800, ge=0)

    # --- Cost control (FR-GN-5) ---
    cost_ceiling_usd_per_request: float = Field(default=0.05, gt=0.0)

    # --- Rate limiting (NFR-SC-2) ---
    rate_limit_max_requests: int = Field(default=30, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)

    # --- Security ---
    admin_bearer_token: SecretStr | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def embedding_dimensions(self) -> int:
        """Number of embedding dimensions implied by :attr:`dimensionality_mode`.

        Returns:
            int: 3072 for ``halfvec_3072``, 1536 for ``vector_1536``.
        """
        return 3072 if self.dimensionality_mode == "halfvec_3072" else 1536

    @model_validator(mode="after")
    def _validate_relationships(self) -> Settings:
        """Enforce cross-field invariants the individual constraints cannot express.

        Returns:
            Settings: The validated instance.

        Raises:
            ValueError: If chunk sizing, retrieval depth, or fusion weights are
                internally inconsistent.
        """
        if self.chunk_max_tokens < self.chunk_target_tokens:
            raise ValueError("chunk_max_tokens must be >= chunk_target_tokens")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("chunk_overlap_tokens must be < chunk_target_tokens")
        if self.retrieval_top_k > self.retrieval_top_n:
            raise ValueError("retrieval_top_k must be <= retrieval_top_n")
        if self.vector_weight == 0.0 and self.lexical_weight == 0.0:
            raise ValueError("at least one of vector_weight or lexical_weight must be > 0")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide, cached settings instance.

    The instance is built once and memoised, so configuration is validated a single
    time per process and shared across the API, workers, and Celery beat.

    Returns:
        Settings: The validated settings for this process.
    """
    return Settings()

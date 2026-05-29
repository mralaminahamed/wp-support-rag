"""Runtime LLM provider/model selection (FR-GN-3, multi-provider abstraction).

Settings supply the env-file defaults (``default_provider`` and the per-provider
model ids). An optional Redis override — written from the admin Settings page —
lets the active provider and model be changed at runtime without an env edit or
restart. Resolution always falls back to the env defaults when no override is
set, so the system is configuration-driven first and override second.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, get_args

from redis.asyncio import Redis

from app.config import EmbeddingProvider, ProviderName, Settings

_OVERRIDE_KEY = "llm:override"
"""Redis key holding the JSON ``{"provider": ..., "model": ...}`` override."""

_EMBED_OVERRIDE_KEY = "embed:override"
"""Redis key holding the JSON ``{"provider": ..., "model": ...}`` embedding override."""

PROVIDERS: tuple[ProviderName, ...] = get_args(ProviderName)
"""All generation provider names the factory can resolve, in display order."""

EMBEDDING_PROVIDERS: tuple[EmbeddingProvider, ...] = get_args(EmbeddingProvider)
"""All embedding provider names, in display order."""

ConfigSource = Literal["override", "env"]


@dataclass(frozen=True)
class EffectiveLLMConfig:
    """The provider and model that will actually be used for generation.

    Attributes:
        provider: Resolved provider name.
        model: Resolved model id for that provider.
        source: ``"override"`` when a Redis override is active, else ``"env"``.
    """

    provider: ProviderName
    model: str
    source: ConfigSource


def env_model(settings: Settings, provider: ProviderName) -> str:
    """Return the env-configured model id for a provider.

    Args:
        settings: Application settings.
        provider: The provider to look up.

    Returns:
        str: The model id from configuration for that provider.

    Raises:
        ValueError: If the provider name is unknown.
    """
    if provider == "anthropic":
        return settings.anthropic_model
    if provider == "openai":
        return settings.openai_model
    if provider == "ollama":
        return settings.ollama_model
    raise ValueError(f"unknown provider: {provider}")


def is_configured(settings: Settings, provider: ProviderName) -> bool:
    """Report whether a provider has the credentials/endpoint it needs.

    Args:
        settings: Application settings.
        provider: The provider to check.

    Returns:
        bool: True when the provider is usable with the current settings.
    """
    if provider == "anthropic":
        return settings.anthropic_api_key is not None
    if provider == "openai":
        return settings.openai_api_key is not None
    if provider == "ollama":
        return bool(settings.ollama_base_url)
    return False


async def get_override(redis: Redis) -> dict[str, str]:
    """Read the raw provider/model override from Redis.

    Args:
        redis: The Redis client.

    Returns:
        dict[str, str]: The stored override, or an empty dict when none is set
        or the stored value is malformed.
    """
    raw = await redis.get(_OVERRIDE_KEY)
    if raw is None:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def set_override(redis: Redis, provider: ProviderName, model: str) -> None:
    """Persist a provider/model override.

    Args:
        redis: The Redis client.
        provider: The provider to activate.
        model: The model id to use for that provider.
    """
    await redis.set(_OVERRIDE_KEY, json.dumps({"provider": provider, "model": model}))


async def clear_override(redis: Redis) -> None:
    """Remove any override, reverting to the env-file defaults.

    Args:
        redis: The Redis client.
    """
    await redis.delete(_OVERRIDE_KEY)


async def resolve(redis: Redis, settings: Settings) -> EffectiveLLMConfig:
    """Resolve the effective provider and model, override taking precedence.

    A stored override is honoured only when its provider is valid; an unknown
    provider falls through to the env default so a stale override can never
    wedge generation.

    Args:
        redis: The Redis client.
        settings: Application settings supplying the defaults.

    Returns:
        EffectiveLLMConfig: The provider, model, and which source won.
    """
    override = await get_override(redis)
    provider = override.get("provider")
    if provider in PROVIDERS:
        model = override.get("model") or env_model(settings, provider)
        return EffectiveLLMConfig(provider=provider, model=model, source="override")
    return EffectiveLLMConfig(
        provider=settings.default_provider,
        model=env_model(settings, settings.default_provider),
        source="env",
    )


@dataclass(frozen=True)
class EffectiveEmbeddingConfig:
    """The embedding provider, model, and width that will be used.

    Attributes:
        provider: Resolved embedding provider name.
        model: Resolved embedding model id.
        dimensions: Vector width for that model (bound to the DB column).
        source: ``"override"`` when a same-dimension override is active, else ``"env"``.
    """

    provider: EmbeddingProvider
    model: str
    dimensions: int
    source: ConfigSource


def embed_model_for(settings: Settings, provider: EmbeddingProvider) -> str:
    """Return the env-configured embedding model id for a provider.

    Args:
        settings: Application settings.
        provider: The embedding provider to look up.

    Returns:
        str: The model id configured for that provider.
    """
    return settings.ollama_embed_model if provider == "ollama" else settings.embed_model


def embed_dims_for(settings: Settings, provider: EmbeddingProvider) -> int:
    """Return the embedding width a provider's configured model produces.

    Args:
        settings: Application settings.
        provider: The embedding provider to look up.

    Returns:
        int: The model's vector width.
    """
    if provider == "ollama":
        return settings.ollama_embed_dimensions
    return 3072 if settings.dimensionality_mode == "halfvec_3072" else 1536


def embedding_configured(settings: Settings, provider: EmbeddingProvider) -> bool:
    """Report whether an embedding provider has its credentials/endpoint.

    Args:
        settings: Application settings.
        provider: The embedding provider to check.

    Returns:
        bool: True when the provider is usable with the current settings.
    """
    if provider == "ollama":
        return bool(settings.ollama_base_url)
    return settings.openai_api_key is not None


async def get_embedding_override(redis: Redis) -> dict[str, str]:
    """Read the raw embedding override from Redis.

    Args:
        redis: The Redis client.

    Returns:
        dict[str, str]: The stored override, or an empty dict when absent/malformed.
    """
    raw = await redis.get(_EMBED_OVERRIDE_KEY)
    if raw is None:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def set_embedding_override(
    redis: Redis, provider: EmbeddingProvider, model: str
) -> None:
    """Persist an embedding provider/model override.

    Args:
        redis: The Redis client.
        provider: The embedding provider to activate.
        model: The embedding model id to use.
    """
    await redis.set(_EMBED_OVERRIDE_KEY, json.dumps({"provider": provider, "model": model}))


async def clear_embedding_override(redis: Redis) -> None:
    """Remove any embedding override, reverting to the env defaults.

    Args:
        redis: The Redis client.
    """
    await redis.delete(_EMBED_OVERRIDE_KEY)


async def resolve_embedding(redis: Redis, settings: Settings) -> EffectiveEmbeddingConfig:
    """Resolve the effective embedding config, honouring a same-width override.

    An override is applied only when its provider is valid and produces vectors of
    the same width as the live DB column (``settings.embedding_dimensions``). A
    different width cannot be applied at runtime — it requires a migration and a
    re-embed — so such an override is ignored here and rejected at the API.

    Args:
        redis: The Redis client.
        settings: Application settings supplying the env defaults and column width.

    Returns:
        EffectiveEmbeddingConfig: The provider, model, width, and source.
    """
    column_dims = settings.embedding_dimensions
    override = await get_embedding_override(redis)
    provider = override.get("provider")
    if provider in EMBEDDING_PROVIDERS and embed_dims_for(settings, provider) == column_dims:
        model = override.get("model") or embed_model_for(settings, provider)
        return EffectiveEmbeddingConfig(
            provider=provider, model=model, dimensions=column_dims, source="override"
        )
    return EffectiveEmbeddingConfig(
        provider=settings.embedding_provider,
        model=settings.active_embed_model,
        dimensions=column_dims,
        source="env",
    )

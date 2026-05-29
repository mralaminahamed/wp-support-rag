"""Provider factory (FR-GN-3, multi-provider abstraction).

Resolves the active :class:`LLMProvider` and its model id from configuration so
Claude, OpenAI, and Ollama are interchangeable without code changes.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from app.config import ProviderName, Settings, get_settings
from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai import OpenAIProvider


def build_provider(settings: Settings, provider_name: ProviderName | None = None) -> LLMProvider:
    """Construct the configured LLM provider.

    Args:
        settings: Application settings.
        provider_name: Override; defaults to ``settings.default_provider``.

    Returns:
        LLMProvider: The resolved provider instance.

    Raises:
        ValueError: If the provider name is unknown.
    """
    name = provider_name or settings.default_provider
    if name == "anthropic":
        return AnthropicProvider(settings)
    if name == "openai":
        return OpenAIProvider(settings)
    if name == "ollama":
        return OllamaProvider(settings)
    raise ValueError(f"unknown provider: {name}")


def active_model(
    settings: Settings | None = None, provider_name: ProviderName | None = None
) -> str:
    """Return the model id for the active (or named) provider.

    Args:
        settings: Application settings; resolved from configuration if omitted.
        provider_name: Override; defaults to ``settings.default_provider``.

    Returns:
        str: The configured model id for the provider.

    Raises:
        ValueError: If the provider name is unknown.
    """
    settings = settings or get_settings()
    name = provider_name or settings.default_provider
    if name == "anthropic":
        return settings.anthropic_model
    if name == "openai":
        return settings.openai_model
    if name == "ollama":
        return settings.ollama_model
    raise ValueError(f"unknown provider: {name}")

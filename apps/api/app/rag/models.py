"""LangChain chat-model factory + provider-error translation.

Replaces the hand-rolled provider classes with ``init_chat_model``. The Redis
runtime override (``app.llm.runtime.resolve``) remains the source of truth for
the effective provider/model; this module only turns that resolved config into a
LangChain ``BaseChatModel``. Gemini and OpenCode Zen are OpenAI-compatible, so
they route through ``ChatOpenAI`` with a provider ``base_url``.

The cost breaker, response cache, retry policy, and degraded/decline paths key on
the ``ProviderUnavailable`` / ``ProviderRejected`` split. LangChain raises
provider-native SDK exceptions, so :func:`classify_provider_error` maps those
back onto that hierarchy, preserving the legacy fail-open semantics.

Gated by ``settings.use_langchain``; unused while the flag is off.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain.chat_models import init_chat_model

from app.config import ProviderName, Settings
from app.llm.base import ProviderError, ProviderRejected, ProviderUnavailable

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from app.llm.runtime import EffectiveLLMConfig

# app provider name -> (LangChain model_provider, extra constructor kwargs).
# Gemini + OpenCode Zen are OpenAI-compatible endpoints.
_PROVIDER_MAP: dict[ProviderName, tuple[str, dict[str, Any]]] = {
    "anthropic": ("anthropic", {}),
    "openai": ("openai", {}),
    "ollama": ("ollama", {}),
    "gemini": ("openai", {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"}),
    "opencode_zen": ("openai", {"base_url": "https://opencode.ai/zen/v1/"}),
}

# Retryable (transient) HTTP status codes → ProviderUnavailable.
_RETRYABLE_STATUS = {408, 409, 425, 429}


def _secret(value: Any) -> str | None:
    """Return the plaintext of a ``SecretStr`` (or ``None``)."""
    return value.get_secret_value() if value is not None else None


def _credentials(settings: Settings, provider: ProviderName) -> dict[str, Any]:
    """Per-provider credential/endpoint kwargs for ``init_chat_model``.

    Args:
        settings: Application settings.
        provider: The app provider name.

    Returns:
        dict[str, Any]: ``api_key`` and/or ``base_url`` for the provider.
    """
    if provider == "anthropic":
        return {"api_key": _secret(settings.anthropic_api_key)}
    if provider == "openai":
        return {"api_key": _secret(settings.openai_api_key)}
    if provider == "gemini":
        return {"api_key": _secret(settings.gemini_api_key)}
    if provider == "opencode_zen":
        return {"api_key": _secret(settings.opencode_zen_api_key)}
    if provider == "ollama":
        return {"base_url": settings.ollama_base_url}
    return {}


def _decode_kwargs(settings: Settings, provider: ProviderName) -> dict[str, Any]:
    """Deterministic decode params, normalised per provider.

    Ollama caps output with ``num_predict`` (not ``max_tokens``) and does not
    accept a ``timeout`` constructor arg; the OpenAI-family and Anthropic use
    ``max_tokens`` + ``timeout``.
    """
    if provider == "ollama":
        return {"temperature": 0.0, "num_predict": settings.llm_max_output_tokens}
    return {
        "temperature": 0.0,
        "max_tokens": settings.llm_max_output_tokens,
        "timeout": settings.llm_timeout_seconds,
    }


def build_chat_model(settings: Settings, cfg: EffectiveLLMConfig) -> BaseChatModel:
    """Build a LangChain chat model for the resolved provider/model.

    Args:
        settings: Application settings (decode params, credentials).
        cfg: Effective provider/model from ``app.llm.runtime.resolve``.

    Returns:
        BaseChatModel: A configured, deterministic chat model.

    Raises:
        ValueError: If the provider name is unknown.
    """
    mapped = _PROVIDER_MAP.get(cfg.provider)
    if mapped is None:
        raise ValueError(f"unknown provider: {cfg.provider}")
    model_provider, extras = mapped
    kwargs: dict[str, Any] = _decode_kwargs(settings, cfg.provider)
    kwargs.update({k: v for k, v in _credentials(settings, cfg.provider).items() if v is not None})
    kwargs.update(extras)
    # model_provider is always concrete here, so a plain BaseChatModel is returned
    # (never the configurable variant).
    model = init_chat_model(model=cfg.model, model_provider=model_provider, **kwargs)
    return cast("BaseChatModel", model)


def _status_code(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction from a provider SDK exception."""
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def classify_provider_error(exc: BaseException) -> type[ProviderError]:
    """Map a LangChain/SDK exception onto the provider-error hierarchy.

    Transient failures (timeouts, connection resets, rate limits, 5xx) become
    :class:`ProviderUnavailable` (retried, then fails open to degraded links).
    Definite client errors (other 4xx) become :class:`ProviderRejected`
    (no retry). Ambiguous errors default to ``ProviderUnavailable`` so a
    transient blip degrades gracefully rather than hard-failing (FR-GN-6).

    Args:
        exc: The raised exception.

    Returns:
        type[ProviderError]: ``ProviderUnavailable`` or ``ProviderRejected``.
    """
    name = type(exc).__name__.lower()
    if any(tok in name for tok in ("timeout", "connect", "network", "apiconnection")):
        return ProviderUnavailable
    status = _status_code(exc)
    if status is not None:
        if status in _RETRYABLE_STATUS or status >= 500:
            return ProviderUnavailable
        if 400 <= status < 500:
            return ProviderRejected
    return ProviderUnavailable

"""Anthropic (Claude) provider (FR-GN-3).

Wraps the Anthropic Messages API with a per-call timeout, bounded retry with
exponential backoff, and structured error mapping. Caching and circuit breaking
are applied by the generator, not here.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import ClassVar

import anthropic
from anthropic import AsyncAnthropic

from apps.api.config import Settings
from apps.api.llm.base import (
    CompletionRequest,
    CompletionResult,
    ProviderRejected,
    ProviderUnavailable,
    TokenUsage,
    call_with_retries,
)

_RETRYABLE = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class AnthropicProvider:
    """Claude generation provider."""

    name: ClassVar[str] = "anthropic"

    def __init__(self, settings: Settings) -> None:
        """Initialise the Anthropic client from configuration.

        Args:
            settings: Application settings supplying the key, timeout, and retries.
        """
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        self._client = AsyncAnthropic(api_key=key, timeout=settings.llm_timeout_seconds)
        self._retries = settings.llm_max_retries

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Generate a completion via the Messages API.

        Args:
            request: The grounded completion request.

        Returns:
            CompletionResult: The model output and token usage.

        Raises:
            ProviderUnavailable: On timeout/outage after retries.
            ProviderRejected: On a non-retryable provider error.
        """
        return await call_with_retries(lambda: self._invoke(request), self._retries)

    async def _invoke(self, request: CompletionRequest) -> CompletionResult:
        """Perform one Messages API call, mapping SDK errors.

        Args:
            request: The grounded completion request.

        Returns:
            CompletionResult: The model output and token usage.

        Raises:
            ProviderUnavailable: On a retryable SDK error.
            ProviderRejected: On any other SDK error.
        """
        try:
            response = await self._client.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
            )
        except _RETRYABLE as exc:
            raise ProviderUnavailable(f"anthropic unavailable: {exc}") from exc
        except anthropic.APIError as exc:
            raise ProviderRejected(f"anthropic rejected: {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return CompletionResult(
            text=text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Stream answer text deltas via the Messages streaming API (FR-DL-3).

        Args:
            request: The grounded completion request.

        Yields:
            str: Text deltas in order.

        Raises:
            ProviderUnavailable: On a retryable SDK error.
            ProviderRejected: On any other SDK error.
        """
        try:
            async with self._client.messages.stream(
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
            ) as stream:
                async for delta in stream.text_stream:
                    yield delta
        except _RETRYABLE as exc:
            raise ProviderUnavailable(f"anthropic unavailable: {exc}") from exc
        except anthropic.APIError as exc:
            raise ProviderRejected(f"anthropic rejected: {exc}") from exc

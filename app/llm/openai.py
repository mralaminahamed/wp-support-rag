"""OpenAI provider (FR-GN-3).

Wraps the OpenAI Chat Completions API with a per-call timeout, bounded retry
with exponential backoff, and structured error mapping. Caching and circuit
breaking are applied by the generator, not here.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from typing import ClassVar

import openai
from openai import AsyncOpenAI

from app.config import Settings
from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    ProviderRejected,
    ProviderUnavailable,
    TokenUsage,
    call_with_retries,
)

_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class OpenAIProvider:
    """OpenAI generation provider."""

    name: ClassVar[str] = "openai"

    def __init__(self, settings: Settings) -> None:
        """Initialise the OpenAI client from configuration.

        Args:
            settings: Application settings supplying the key, timeout, and retries.
        """
        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        self._client = AsyncOpenAI(api_key=key, timeout=settings.llm_timeout_seconds)
        self._retries = settings.llm_max_retries

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Generate a completion via the Chat Completions API.

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
        """Perform one Chat Completions call, mapping SDK errors.

        Args:
            request: The grounded completion request.

        Returns:
            CompletionResult: The model output and token usage.

        Raises:
            ProviderUnavailable: On a retryable SDK error.
            ProviderRejected: On any other SDK error.
        """
        try:
            response = await self._client.chat.completions.create(
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
            )
        except _RETRYABLE as exc:
            raise ProviderUnavailable(f"openai unavailable: {exc}") from exc
        except openai.APIError as exc:
            raise ProviderRejected(f"openai rejected: {exc}") from exc

        text = response.choices[0].message.content or ""
        usage = response.usage
        return CompletionResult(
            text=text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

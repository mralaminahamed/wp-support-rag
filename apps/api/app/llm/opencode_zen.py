"""OpenCode Zen provider via OpenAI-compatible endpoint (FR-GN-3).

OpenCode Zen is a curated set of models tested for coding agents, served at
https://opencode.ai/zen/v1. No extra dependency is needed beyond the openai
package already present. Streaming is supported.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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

_OPENCODE_ZEN_BASE_URL = "https://opencode.ai/zen/v1/"

_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class OpenCodeZenProvider:
    """OpenCode Zen generation provider (OpenAI-compatible endpoint)."""

    name: ClassVar[str] = "opencode_zen"
    title: ClassVar[str] = "OpenCode Zen"
    default_model_id: ClassVar[str] = "opencode/claude-sonnet-4-6"
    available_models: ClassVar[list[str]] = [
        "opencode/claude-sonnet-4-6",
        "opencode/claude-opus-4-7",
        "opencode/claude-haiku-4-5",
        "opencode/gpt-5.5",
        "opencode/gpt-5.1",
        "opencode/gpt-5.1-codex",
        "opencode/gemini-3.5-flash",
        "opencode/gemini-3.1-pro",
        "opencode/deepseek-v4-flash-free",
        "opencode/big-pickle",
        "opencode/qwen3.5-plus",
        "opencode/kimi-k2.6",
    ]

    def __init__(self, settings: Settings) -> None:
        key = settings.opencode_zen_api_key.get_secret_value() if settings.opencode_zen_api_key else None
        self._client = AsyncOpenAI(
            api_key=key,
            base_url=_OPENCODE_ZEN_BASE_URL,
            timeout=settings.llm_timeout_seconds,
        )
        self._retries = settings.llm_max_retries

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        return await call_with_retries(lambda: self._invoke(request), self._retries)

    async def _invoke(self, request: CompletionRequest) -> CompletionResult:
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
            raise ProviderUnavailable(f"opencode_zen unavailable: {exc}") from exc
        except openai.APIError as exc:
            raise ProviderRejected(f"opencode_zen rejected: {exc}") from exc

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

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                stream=True,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except _RETRYABLE as exc:
            raise ProviderUnavailable(f"opencode_zen unavailable: {exc}") from exc
        except openai.APIError as exc:
            raise ProviderRejected(f"opencode_zen rejected: {exc}") from exc

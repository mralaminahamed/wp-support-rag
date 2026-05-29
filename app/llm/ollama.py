"""Ollama provider (FR-GN-3).

Wraps a local Ollama server's chat API over async ``httpx`` with a per-call
timeout, bounded retry with exponential backoff, and structured error mapping.
Caching and circuit breaking are applied by the generator, not here.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from app.config import Settings
from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    ProviderRejected,
    ProviderUnavailable,
    TokenUsage,
    call_with_retries,
)


class OllamaProvider:
    """Local Ollama generation provider."""

    name: ClassVar[str] = "ollama"

    def __init__(self, settings: Settings) -> None:
        """Initialise the Ollama client from configuration.

        Args:
            settings: Application settings supplying base URL, timeout, and retries.
        """
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout = settings.llm_timeout_seconds
        self._retries = settings.llm_max_retries

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Generate a completion via the Ollama chat API.

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
        """Perform one chat call, mapping transport and status errors.

        Args:
            request: The grounded completion request.

        Returns:
            CompletionResult: The model output and token usage.

        Raises:
            ProviderUnavailable: On a transport error or 5xx status.
            ProviderRejected: On a 4xx status.
        """
        payload: dict[str, Any] = {
            "model": request.model,
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"ollama unavailable: {exc}") from exc

        if response.status_code >= 500:
            raise ProviderUnavailable(f"ollama unavailable: {response.status_code}")
        if response.status_code >= 400:
            raise ProviderRejected(f"ollama rejected: {response.status_code}")

        data = response.json()
        return CompletionResult(
            text=data["message"]["content"],
            model=data.get("model", request.model),
            usage=TokenUsage(
                input_tokens=int(data.get("prompt_eval_count", 0)),
                output_tokens=int(data.get("eval_count", 0)),
            ),
        )

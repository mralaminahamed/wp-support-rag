"""Provider-agnostic LLM interface (§2.5, FR-GN-3).

Defines the :class:`LLMProvider` protocol that Claude, OpenAI, and Ollama
implementations satisfy, the request/result models, the structured error
hierarchy (:class:`ProviderUnavailable` vs :class:`ProviderRejected`), and a
shared bounded-retry helper. Providers apply timeout, retry, and error mapping
only; caching and circuit breaking are cross-cutting and live elsewhere.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_MAX_BACKOFF_SECONDS = 30.0


class ProviderError(Exception):
    """Base class for all provider errors."""


class ProviderUnavailable(ProviderError):  # noqa: N818 - name fixed by architecture §2.5
    """A transient outage: timeout, connection error, rate limit, or 5xx.

    Retryable; after retries are exhausted the generator fails open (FR-GN-6).
    """


class ProviderRejected(ProviderError):  # noqa: N818 - name fixed by architecture §2.5
    """A non-retryable provider error: bad request, auth, or content rejection."""


class CompletionRequest(BaseModel):
    """A grounded completion request.

    Attributes:
        system: System prompt holding the instructions.
        user: User message holding the fenced question and retrieved context.
        model: Resolved model identifier to call.
        max_tokens: Maximum completion tokens to generate.
        temperature: Sampling temperature (deterministic by default).
        stream: Whether the caller intends to stream the response.
    """

    system: str
    user: str
    model: str
    max_tokens: int
    temperature: float = 0.0
    stream: bool = False


class TokenUsage(BaseModel):
    """Token accounting for a completion.

    Attributes:
        input_tokens: Tokens consumed by the prompt.
        output_tokens: Tokens generated in the completion.
    """

    input_tokens: int
    output_tokens: int


class CompletionResult(BaseModel):
    """The result of a completion.

    Attributes:
        text: The generated text.
        model: The model id that produced the result.
        usage: Token usage for the call.
    """

    text: str
    model: str
    usage: TokenUsage


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface (§2.5).

    Implementations wrap a single backend and must apply timeout, bounded retry
    with exponential backoff, and structured error mapping. They must not
    implement caching or circuit breaking.
    """

    name: ClassVar[str]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Produce a completion for the given grounded request.

        Args:
            request: System prompt, grounded user content, and decode params.

        Returns:
            CompletionResult: Text, token usage, and resolved model id.

        Raises:
            ProviderUnavailable: On timeout or outage after retries.
            ProviderRejected: On a non-retryable provider error.
        """
        ...


async def call_with_retries(
    operation: Callable[[], Awaitable[CompletionResult]], retries: int
) -> CompletionResult:
    """Invoke a completion operation with bounded exponential backoff.

    Retries only on :class:`ProviderUnavailable`; :class:`ProviderRejected`
    propagates immediately.

    Args:
        operation: A zero-arg coroutine factory performing one provider call.
        retries: Maximum number of retries after the first attempt.

    Returns:
        CompletionResult: The successful result.

    Raises:
        ProviderUnavailable: If all attempts fail.
        ProviderRejected: On the first non-retryable error.
    """
    for attempt in range(retries + 1):
        try:
            return await operation()
        except ProviderUnavailable:
            if attempt >= retries:
                raise
            delay = min(2.0**attempt, _MAX_BACKOFF_SECONDS)
            logger.warning("retrying provider call", extra={"attempt": attempt, "delay_s": delay})
            await asyncio.sleep(delay)
    raise ProviderUnavailable("retries exhausted")  # pragma: no cover - loop always returns/raises

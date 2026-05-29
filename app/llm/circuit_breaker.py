"""Cost circuit breaker (FR-GN-5).

Estimates the projected token cost of a generation call and refuses calls
projected to exceed the configured per-request ceiling. During streaming, the
running output is checked so an overrun aborts before more cost accrues.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from app.config import Settings
from app.llm.base import CompletionRequest
from app.processing.chunker import count_tokens


class CostCeilingExceeded(Exception):  # noqa: N818 - domain term from FR-GN-5
    """Raised when a call is projected to exceed the configured cost ceiling."""


class CostCircuitBreaker:
    """Projects per-request cost and enforces the configured ceiling (FR-GN-5)."""

    def __init__(self, settings: Settings) -> None:
        """Initialise from configuration.

        Args:
            settings: Application settings supplying the ceiling and token prices.
        """
        self._ceiling = settings.cost_ceiling_usd_per_request
        self._input_price = settings.cost_per_1k_input_usd
        self._output_price = settings.cost_per_1k_output_usd

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the USD cost of a call.

        Args:
            input_tokens: Prompt token count.
            output_tokens: Completion token count.

        Returns:
            float: Projected cost in USD.
        """
        return (
            input_tokens / 1000.0 * self._input_price + output_tokens / 1000.0 * self._output_price
        )

    def guard(self, request: CompletionRequest) -> float:
        """Refuse a request projected to exceed the ceiling (FR-GN-5).

        The projection assumes the full ``max_tokens`` are generated, the
        worst case for cost.

        Args:
            request: The completion request to check.

        Returns:
            float: The projected cost (when under the ceiling).

        Raises:
            CostCeilingExceeded: If the projected cost exceeds the ceiling.
        """
        input_tokens = count_tokens(request.system) + count_tokens(request.user)
        projected = self.estimate_cost(input_tokens, request.max_tokens)
        if projected > self._ceiling:
            raise CostCeilingExceeded(
                f"projected ${projected:.4f} exceeds ceiling ${self._ceiling:.4f}"
            )
        return projected

    def overruns(self, input_tokens: int, output_tokens_so_far: int) -> bool:
        """Report whether a streaming response has exceeded the ceiling.

        Args:
            input_tokens: Prompt token count.
            output_tokens_so_far: Output tokens generated so far.

        Returns:
            bool: ``True`` if the run so far already exceeds the ceiling and
            streaming should abort.
        """
        return self.estimate_cost(input_tokens, output_tokens_so_far) > self._ceiling

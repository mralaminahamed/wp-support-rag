"""Unit tests for prompts, cache key, circuit breaker, citations, factory, retry."""

from __future__ import annotations

import uuid

import pytest
from apps.api.config import Settings
from apps.api.llm.base import (
    CompletionRequest,
    CompletionResult,
    ProviderRejected,
    ProviderUnavailable,
    TokenUsage,
    call_with_retries,
)
from apps.api.llm.cache import cache_key
from apps.api.llm.circuit_breaker import CostCeilingExceeded, CostCircuitBreaker
from apps.api.llm.factory import active_model, build_provider
from apps.api.prompts.registry import PromptRegistry, PromptVersion, get_registry
from apps.api.rag.generator import validate_citations
from apps.api.rag.retriever import RetrievedChunk

CHUNK_IDS = [uuid.UUID(int=1), uuid.UUID(int=2)]


def _chunk(url: str, content: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        plugin_id=uuid.uuid4(),
        content=content,
        heading_path=None,
        source_url=url,
        score=0.5,
    )


def test_active_prompt_resolves_and_fences_blocks() -> None:
    """The active support_answer version renders fenced untrusted blocks (NFR-SC-3)."""
    version = get_registry().active("support_answer")
    assert version.status == "active"

    rendered = version.render("How do I do X?", [_chunk("https://example.com/a", "Do X like so.")])
    assert "<user_question>" in rendered and "</user_question>" in rendered
    assert "<retrieved_context>" in rendered
    assert "How do I do X?" in rendered
    assert "https://example.com/a" in rendered


def test_registry_rejects_second_active_version() -> None:
    """Registering two active versions for a family is an error (ADR-005)."""
    reg = PromptRegistry()
    base = PromptVersion("f", "1", "active", "sys", lambda q, c: q, "first")
    reg.register(base)
    with pytest.raises(ValueError, match="already has an active"):
        reg.register(PromptVersion("f", "2", "active", "sys", lambda q, c: q, "second"))


def test_cache_key_is_stable_and_context_sensitive() -> None:
    """The cache key is deterministic and changes with the context fingerprint."""
    a = cache_key("How do I X?", CHUNK_IDS, "m", "v1")
    b = cache_key("how do  i x?", CHUNK_IDS, "m", "v1")  # normalised whitespace/case
    c = cache_key("How do I X?", list(reversed(CHUNK_IDS)), "m", "v1")
    assert a == b
    assert a != c
    assert a.startswith("answer:")


def test_circuit_breaker_refuses_oversized_request() -> None:
    """A request projected to exceed the ceiling is refused (FR-GN-5)."""
    request = CompletionRequest(system="s", user="u", model="m", max_tokens=100_000)
    with pytest.raises(CostCeilingExceeded):
        CostCircuitBreaker(Settings(cost_ceiling_usd_per_request=0.0001)).guard(request)


def test_circuit_breaker_allows_small_request() -> None:
    """A small request passes and returns a projected cost."""
    request = CompletionRequest(system="s", user="hello", model="m", max_tokens=50)
    cost = CostCircuitBreaker(Settings()).guard(request)
    assert cost >= 0.0


def test_citation_validation_strips_fabricated_urls() -> None:
    """Only supplied URLs survive; fabricated URLs are stripped (FR-GN-8)."""
    allowed = {"https://example.com/real"}
    text = "See https://example.com/real and https://evil.com/fake for details."
    cleaned, cited = validate_citations(text, allowed)

    assert cited == ["https://example.com/real"]
    assert "evil.com" not in cleaned
    assert "https://example.com/real" in cleaned


def test_factory_resolves_providers_and_models() -> None:
    """The factory resolves each provider and its configured model (FR-GN-3)."""
    settings = Settings(anthropic_api_key="x", openai_api_key="y")
    assert build_provider(settings, "anthropic").name == "anthropic"
    assert build_provider(settings, "openai").name == "openai"
    assert build_provider(settings, "ollama").name == "ollama"
    assert active_model(settings, "anthropic") == settings.anthropic_model
    assert active_model(settings, "openai") == settings.openai_model


async def test_call_with_retries_recovers_then_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries on ProviderUnavailable, succeeds, and gives up after the ceiling."""
    from apps.api.llm import base

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(base.asyncio, "sleep", _no_sleep)
    state = {"n": 0}

    async def flaky() -> CompletionResult:
        state["n"] += 1
        if state["n"] < 2:
            raise ProviderUnavailable("transient")
        return CompletionResult(
            text="ok", model="m", usage=TokenUsage(input_tokens=1, output_tokens=1)
        )

    result = await call_with_retries(flaky, retries=3)
    assert result.text == "ok" and state["n"] == 2

    async def always_down() -> CompletionResult:
        raise ProviderUnavailable("down")

    with pytest.raises(ProviderUnavailable):
        await call_with_retries(always_down, retries=0)

    async def rejected() -> CompletionResult:
        raise ProviderRejected("bad")

    with pytest.raises(ProviderRejected):
        await call_with_retries(rejected, retries=3)

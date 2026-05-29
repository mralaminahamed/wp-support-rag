"""Tests for eval metrics and the offline harness (FR-EV-*)."""

from __future__ import annotations

import pytest
from app.config import get_settings
from app.prompts.registry import PromptRegistry, PromptVersion
from app.rag import generator as generator_module
from eval.harness import (
    CITATION_ACCURACY_THRESHOLD,
    CONTEXT_RECALL_THRESHOLD,
    DeterministicEmbeddingClient,
    ScriptedProvider,
    evaluate,
    load_golden,
)
from eval.metrics import (
    citation_is_accurate,
    is_faithful,
    normalized_edit_distance,
    source_in_results,
)

from tests.conftest import database_available


def test_dataset_meets_spec() -> None:
    """The golden dataset spans the required categories with >=30 records (§6)."""
    records = load_golden()
    assert len(records) >= 30
    categories = {r.category for r in records}
    assert {
        "installation",
        "configuration",
        "troubleshooting",
        "compatibility",
        "billing",
        "unanswerable",
    } <= categories
    assert sum(r.category == "unanswerable" for r in records) >= 5


def test_metric_helpers() -> None:
    """The pure metric helpers behave as specified."""
    assert normalized_edit_distance("abc", "abc") == 0.0
    assert normalized_edit_distance("", "") == 0.0
    assert 0.0 < normalized_edit_distance("abc", "abd") < 1.0
    assert source_in_results(["plug", "faq"], ["https://x/plug/#faq"])
    assert not source_in_results(["plug", "faq"], ["https://x/other"])
    assert not source_in_results([], ["https://x"])
    assert citation_is_accurate(["a"], ["https://x/a"])
    assert is_faithful(["u1"], ["u1", "u2"])
    assert not is_faithful(["bad"], ["u1"])


@pytest.fixture
async def _eval_ready() -> None:
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")


async def test_harness_meets_thresholds(_eval_ready: None) -> None:
    """The committed dataset meets the gated thresholds on the offline harness (§5)."""
    settings = get_settings()
    metrics = await evaluate(
        settings, DeterministicEmbeddingClient(settings.embedding_dimensions), ScriptedProvider()
    )

    assert metrics.context_recall >= CONTEXT_RECALL_THRESHOLD
    assert metrics.citation_accuracy >= CITATION_ACCURACY_THRESHOLD
    assert metrics.n_records >= 30


async def test_regressed_prompt_fails_citation_gate(
    _eval_ready: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt whose render drops the sources fails the citation gate (FR-EV-3)."""

    def _bad_render(question: str, chunks: object) -> str:
        return f"<user_question>\n{question}\n</user_question>"

    bad = PromptVersion(
        family="support_answer",
        version="regressed",
        status="active",
        system="ignore context",
        render=_bad_render,
        changelog="deliberately regressed: drops retrieved context and sources",
    )
    regressed = PromptRegistry()
    regressed.register(bad)
    monkeypatch.setattr(generator_module, "get_registry", lambda: regressed)

    settings = get_settings()
    metrics = await evaluate(
        settings, DeterministicEmbeddingClient(settings.embedding_dimensions), ScriptedProvider()
    )

    assert metrics.citation_accuracy < CITATION_ACCURACY_THRESHOLD

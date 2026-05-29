"""Tests for configuration loading and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.config import Settings


def test_defaults_are_internally_consistent() -> None:
    """The documented defaults load and satisfy every cross-field invariant."""
    settings = Settings()

    assert settings.dimensionality_mode == "halfvec_3072"
    assert settings.embedding_dimensions == 3072
    assert settings.embed_batch_size <= 100
    assert settings.rrf_k == 60


def test_vector_1536_mode_reports_reduced_dimensions() -> None:
    """The pgvector < 0.7.0 fallback exposes 1536 dimensions (NFR-PT-2)."""
    settings = Settings(dimensionality_mode="vector_1536")

    assert settings.embedding_dimensions == 1536


def test_chunk_max_below_target_is_rejected() -> None:
    """A max chunk size smaller than the target fails validation on load."""
    with pytest.raises(ValidationError):
        Settings(chunk_target_tokens=512, chunk_max_tokens=256)


def test_top_k_above_top_n_is_rejected() -> None:
    """Requesting more final chunks than candidates fails validation."""
    with pytest.raises(ValidationError):
        Settings(retrieval_top_n=4, retrieval_top_k=8)


def test_both_fusion_weights_zero_is_rejected() -> None:
    """At least one retrieval signal must carry weight."""
    with pytest.raises(ValidationError):
        Settings(vector_weight=0.0, lexical_weight=0.0)


def test_invalid_provider_is_rejected() -> None:
    """An unknown default provider fails validation."""
    with pytest.raises(ValidationError):
        Settings(default_provider="gemini")  # type: ignore[arg-type]

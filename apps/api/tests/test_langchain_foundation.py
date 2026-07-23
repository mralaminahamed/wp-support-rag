"""Unit tests for the LangChain migration foundation (flag-gated layer).

Covers the pieces that need no database, Redis, or network: the embeddings
adapter's delegation, the chat-model factory + provider map, provider-error
classification, and the ``use_langchain`` dimensionality guard. Integration of
the vector store, LangGraph generation, and re-ingest is verified separately
against a live stack.
"""

from __future__ import annotations

import pytest
from app.config import ProviderName, Settings
from app.llm.base import ProviderRejected, ProviderUnavailable
from app.llm.runtime import EffectiveLLMConfig
from app.rag import embeddings as emb
from app.rag.embeddings import WpragEmbeddings
from app.rag.models import _PROVIDER_MAP, build_chat_model, classify_provider_error
from pydantic import ValidationError


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "anthropic_api_key": "x",
        "openai_api_key": "x",
        "gemini_api_key": "x",
        "opencode_zen_api_key": "x",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --- WpragEmbeddings ---------------------------------------------------------


async def test_embeddings_aembed_query_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_embed_texts(
        client: object, texts: list[str], settings: object
    ) -> list[list[float]]:
        captured["texts"] = texts
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed_texts)
    vec = await WpragEmbeddings(_settings()).aembed_query("hello")
    assert vec == [0.1, 0.2, 0.3]
    assert captured["texts"] == ["hello"]


async def test_embeddings_aembed_documents_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed_texts(
        client: object, texts: list[str], settings: object
    ) -> list[list[float]]:
        return [[float(len(t))] for t in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed_texts)
    out = await WpragEmbeddings(_settings()).aembed_documents(["a", "bb"])
    assert out == [[1.0], [2.0]]


def test_embeddings_sync_methods_raise() -> None:
    e = WpragEmbeddings(_settings())
    with pytest.raises(NotImplementedError):
        e.embed_query("x")
    with pytest.raises(NotImplementedError):
        e.embed_documents(["x"])


# --- Chat-model factory ------------------------------------------------------


def test_provider_map_covers_all_providers() -> None:
    from typing import get_args

    assert set(get_args(ProviderName)) <= set(_PROVIDER_MAP)


@pytest.mark.parametrize(
    ("provider", "model", "expected"),
    [
        ("anthropic", "claude-sonnet-4-6", "ChatAnthropic"),
        ("openai", "gpt-4o-mini", "ChatOpenAI"),
        ("gemini", "gemini-2.0-flash", "ChatOpenAI"),
        ("opencode_zen", "big-pickle", "ChatOpenAI"),
        ("ollama", "llama3.2", "ChatOllama"),
    ],
)
def test_build_chat_model_constructs(provider: str, model: str, expected: str) -> None:
    cfg = EffectiveLLMConfig(provider=provider, model=model, source="env")  # type: ignore[arg-type]
    chat = build_chat_model(_settings(), cfg)
    assert type(chat).__name__ == expected
    assert hasattr(chat, "ainvoke")


def test_build_chat_model_unknown_provider() -> None:
    cfg = EffectiveLLMConfig(provider="bogus", model="m", source="env")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown provider"):
        build_chat_model(_settings(), cfg)


# --- Provider-error classification ------------------------------------------


class _StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_StatusError(503), ProviderUnavailable),
        (_StatusError(500), ProviderUnavailable),
        (_StatusError(429), ProviderUnavailable),
        (_StatusError(408), ProviderUnavailable),
        (_StatusError(400), ProviderRejected),
        (_StatusError(401), ProviderRejected),
        (_StatusError(404), ProviderRejected),
        (TimeoutError(), ProviderUnavailable),
        (ValueError("weird"), ProviderUnavailable),
    ],
)
def test_classify_provider_error(exc: BaseException, expected: type) -> None:
    assert classify_provider_error(exc) is expected


# --- use_langchain dimensionality guard -------------------------------------


def test_use_langchain_rejects_halfvec_3072() -> None:
    # embedding_provider defaults to "openai" → 3072 dims → over the 2000 cap.
    with pytest.raises(ValidationError):
        _settings(use_langchain=True, dimensionality_mode="halfvec_3072")


def test_use_langchain_allows_vector_1536() -> None:
    s = _settings(use_langchain=True, dimensionality_mode="vector_1536")
    assert s.embedding_dimensions == 1536


def test_use_langchain_allows_ollama_768() -> None:
    s = _settings(use_langchain=True, embedding_provider="ollama")
    assert s.embedding_dimensions == 768


def test_legacy_default_allows_halfvec_3072() -> None:
    # With the flag off, the legacy 3072/halfvec default remains valid.
    s = _settings(use_langchain=False, dimensionality_mode="halfvec_3072")
    assert s.embedding_dimensions == 3072

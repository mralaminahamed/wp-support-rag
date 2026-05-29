"""Provider error-mapping tests (structured ProviderUnavailable vs Rejected)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.config import Settings
from app.llm.base import CompletionRequest, ProviderRejected, ProviderUnavailable
from app.llm.ollama import OllamaProvider

REQUEST = CompletionRequest(system="s", user="u", model="llama3.1", max_tokens=64)


class _Resp:
    """Minimal stand-in for an httpx response."""

    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self._payload


def _patch_post(monkeypatch: pytest.MonkeyPatch, behaviour: Any) -> None:
    async def _post(self: httpx.AsyncClient, url: str, json: Any = None) -> _Resp:
        if isinstance(behaviour, Exception):
            raise behaviour
        return behaviour

    monkeypatch.setattr(httpx.AsyncClient, "post", _post)


async def test_ollama_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 response is parsed into a CompletionResult."""
    _patch_post(
        monkeypatch,
        _Resp(
            200,
            {
                "model": "llama3.1",
                "message": {"content": "hi"},
                "prompt_eval_count": 5,
                "eval_count": 3,
            },
        ),
    )
    result = await OllamaProvider(Settings()).complete(REQUEST)
    assert result.text == "hi"
    assert result.usage.input_tokens == 5 and result.usage.output_tokens == 3


async def test_ollama_transport_error_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transport error maps to ProviderUnavailable."""
    _patch_post(monkeypatch, httpx.ConnectError("refused"))
    with pytest.raises(ProviderUnavailable):
        await OllamaProvider(Settings(llm_max_retries=0)).complete(REQUEST)


async def test_ollama_5xx_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 5xx status maps to ProviderUnavailable."""
    _patch_post(monkeypatch, _Resp(503))
    with pytest.raises(ProviderUnavailable):
        await OllamaProvider(Settings(llm_max_retries=0)).complete(REQUEST)


async def test_ollama_4xx_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 4xx status maps to the non-retryable ProviderRejected."""
    _patch_post(monkeypatch, _Resp(400))
    with pytest.raises(ProviderRejected):
        await OllamaProvider(Settings(llm_max_retries=2)).complete(REQUEST)

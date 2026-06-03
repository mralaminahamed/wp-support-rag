"""Unit tests for WebpageAdapter."""

from __future__ import annotations

import pytest
import respx
import httpx

from app.config import get_settings
from app.ingestion.adapters.base import SourceContext, SourceFetchError
from app.ingestion.adapters.webpage import WebpageAdapter


def _ctx(config: dict) -> SourceContext:
    return SourceContext(plugin_slug="test-plugin", source_type="webpage", config=config)


@pytest.mark.asyncio
async def test_webpage_adapter_no_url_raises():
    adapter = WebpageAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="config.url"):
        async for _ in adapter.fetch(_ctx({})):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_fetches_start_url():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text="<html><head><title>Hello</title></head><body><main>Content here</main></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    adapter = WebpageAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({"url": "http://example.com/", "max_depth": 0}))]
    assert len(docs) == 1
    assert docs[0].external_id == "http://example.com/"
    assert docs[0].title == "Hello"
    assert docs[0].content_type == "html"
    assert docs[0].doc_type == "webpage"


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_follows_links():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><main>Root</main><a href="/page2">p2</a></body></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("http://example.com/page2").mock(
        return_value=httpx.Response(
            200,
            text="<html><body><main>Page 2</main></body></html>",
            headers={"content-type": "text/html"},
        )
    )
    adapter = WebpageAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({"url": "http://example.com/", "max_depth": 1}))]
    urls = {d.external_id for d in docs}
    assert "http://example.com/" in urls
    assert "http://example.com/page2" in urls


@pytest.mark.asyncio
@respx.mock
async def test_webpage_adapter_respects_url_filter():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><a href="/docs/page">docs</a><a href="http://other.com/">ext</a></body></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("http://example.com/docs/page").mock(
        return_value=httpx.Response(200, text="<html><body>docs</body></html>",
                                     headers={"content-type": "text/html"})
    )
    adapter = WebpageAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({"url": "http://example.com/", "max_depth": 1,
                  "url_filter": r"^http://example\.com/docs/"})
        )
    ]
    urls = {d.external_id for d in docs}
    assert "http://example.com/docs/page" in urls
    assert "http://other.com/" not in urls

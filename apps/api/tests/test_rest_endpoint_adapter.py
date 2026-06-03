"""Unit tests for RestEndpointAdapter."""

from __future__ import annotations

import pytest
import respx
import httpx

from app.config import get_settings
from app.ingestion.adapters.base import SourceContext, SourceFetchError
from app.ingestion.adapters.rest_endpoint import RestEndpointAdapter


def _ctx(config: dict) -> SourceContext:
    return SourceContext(plugin_slug="test-plugin", source_type="rest_endpoint", config=config)


BASE_CFG = {
    "url": "http://api.example.com/items",
    "id_field": "id",
    "content_field": "body",
}


@pytest.mark.asyncio
async def test_missing_url_raises():
    adapter = RestEndpointAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="config.url"):
        async for _ in adapter.fetch(_ctx({"id_field": "id", "content_field": "body"})):
            pass


@pytest.mark.asyncio
async def test_missing_content_field_raises():
    adapter = RestEndpointAdapter(get_settings())
    with pytest.raises(SourceFetchError, match="content_field"):
        async for _ in adapter.fetch(_ctx({"url": "http://x.com", "id_field": "id"})):
            pass


@pytest.mark.asyncio
@respx.mock
async def test_fetch_single_page():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json=[
            {"id": "1", "body": "Hello world", "title": "Post 1"},
            {"id": "2", "body": "Second post"},
        ])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({**BASE_CFG, "title_field": "title"}))]
    assert len(docs) == 2
    assert docs[0].external_id == "1"
    assert docs[0].content == "Hello world"
    assert docs[0].title == "Post 1"
    assert docs[1].title is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_paginated_page_param():
    respx.get("http://api.example.com/items", params={"page": "1", "per_page": "2"}).mock(
        return_value=httpx.Response(200, json=[{"id": "1", "body": "a"}, {"id": "2", "body": "b"}])
    )
    respx.get("http://api.example.com/items", params={"page": "2", "per_page": "2"}).mock(
        return_value=httpx.Response(200, json=[{"id": "3", "body": "c"}])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({**BASE_CFG, "pagination": "page_param", "page_size": 2})
        )
    ]
    assert [d.external_id for d in docs] == ["1", "2", "3"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_items_path():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json={"data": {"results": [{"id": "1", "body": "x"}]}})
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [doc async for doc in adapter.fetch(_ctx({**BASE_CFG, "items_path": "data.results"}))]
    assert len(docs) == 1
    assert docs[0].external_id == "1"


@pytest.mark.asyncio
@respx.mock
async def test_bearer_auth_header():
    respx.get("http://api.example.com/items").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "body": "secret"}])
    )
    adapter = RestEndpointAdapter(get_settings())
    docs = [
        doc async for doc in adapter.fetch(
            _ctx({**BASE_CFG, "headers": {"Authorization": "Bearer tok123"}})
        )
    ]
    assert len(docs) == 1
    sent_req = respx.calls[0].request
    assert sent_req.headers["authorization"] == "Bearer tok123"

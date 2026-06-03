"""REST endpoint source adapter.

Fetches a paginated JSON API and maps each item to a RawDocument using
configured field paths. Supports four pagination strategies: none, page_param,
link_header, and cursor.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from app.config import Settings, get_settings
from app.ingestion.adapters._http import build_client
from app.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def _get_nested(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path in a nested dict, e.g. 'data.results'."""
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


class RestEndpointAdapter:
    """Adapter for paginated JSON REST APIs."""

    handles: ClassVar[tuple[str, ...]] = ("rest_endpoint",)

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Fetch all pages from the REST endpoint and yield one RawDocument per item."""
        cfg = ctx.config
        base_url: str = cfg.get("url", "")
        if not base_url:
            raise SourceFetchError("rest_endpoint source requires config.url")
        content_field: str = cfg.get("content_field", "")
        if not content_field:
            raise SourceFetchError("rest_endpoint source requires config.content_field")
        id_field: str = cfg.get("id_field", "")
        if not id_field:
            raise SourceFetchError("rest_endpoint source requires config.id_field")

        method: str = cfg.get("method", "GET").upper()
        extra_headers: dict[str, str] = cfg.get("headers", {})
        query_params: dict[str, str] = dict(cfg.get("query_params", {}))
        pagination: str = cfg.get("pagination", "none")
        page_param: str = cfg.get("page_param", "page")
        page_size_param: str = cfg.get("page_size_param", "per_page")
        page_size: int = int(cfg.get("page_size", 100))
        cursor_field: str = cfg.get("cursor_field", "")
        items_path: str = cfg.get("items_path", "")
        title_field: str = cfg.get("title_field", "")
        url_field: str = cfg.get("url_field", "")

        async with build_client(self._settings, headers=extra_headers) as client:
            if pagination == "page_param":
                async for doc in self._fetch_page_param(
                    client, base_url, method, query_params,
                    page_param, page_size_param, page_size, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc
            elif pagination == "link_header":
                async for doc in self._fetch_link_header(
                    client, base_url, method, query_params, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc
            elif pagination == "cursor":
                async for doc in self._fetch_cursor(
                    client, base_url, method, query_params, cursor_field, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc
            else:  # "none"
                async for doc in self._fetch_single(
                    client, base_url, method, query_params, items_path,
                    id_field, content_field, title_field, url_field, ctx,
                ):
                    yield doc

    def _item_to_doc(
        self,
        item: dict[str, Any],
        id_field: str,
        content_field: str,
        title_field: str,
        url_field: str,
        ctx: SourceContext,
    ) -> RawDocument | None:
        """Map one API item dict to a RawDocument, or None if required fields missing."""
        external_id = str(item.get(id_field, ""))
        content = str(item.get(content_field, ""))
        if not external_id or not content:
            return None
        title = str(item.get(title_field, "")) if title_field else None
        source_url = str(item.get(url_field, "")) if url_field else ctx.config.get("url", "")
        return RawDocument(
            external_id=external_id,
            title=title or None,
            doc_type="rest_endpoint",
            content=content,
            content_type="text",
            source_url=source_url,
            metadata={"plugin_slug": ctx.plugin_slug},
        )

    async def _request_json(
        self, client: Any, method: str, url: str, params: dict
    ) -> tuple[Any, dict]:
        """Make a request and return (parsed_json, response_headers)."""
        resp = await client.request(method, url, params=params)
        if resp.status_code != 200:
            raise SourceFetchError(
                f"rest_endpoint returned HTTP {resp.status_code} for {url}"
            )
        return resp.json(), dict(resp.headers)

    async def _fetch_single(
        self, client: Any, url: str, method: str, params: dict,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        data, _ = await self._request_json(client, method, url, params)
        items = _get_nested(data, items_path) if items_path else data
        if not isinstance(items, list):
            items = [items] if isinstance(items, dict) else []
        for item in items:
            doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
            if doc:
                yield doc

    async def _fetch_page_param(
        self, client: Any, url: str, method: str, params: dict,
        page_param: str, page_size_param: str, page_size: int,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        page = 1
        while True:
            p = {**params, page_param: str(page), page_size_param: str(page_size)}
            data, _ = await self._request_json(client, method, url, p)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list) or not items:
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            if len(items) < page_size:
                break
            page += 1

    async def _fetch_link_header(
        self, client: Any, url: str, method: str, params: dict,
        items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        next_url: str | None = url
        while next_url:
            data, headers = await self._request_json(client, method, next_url, params)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list):
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            link_header = headers.get("link", "")
            match = _LINK_RE.search(link_header)
            next_url = match.group(1) if match else None
            params = {}  # next_url already has params baked in

    async def _fetch_cursor(
        self, client: Any, url: str, method: str, params: dict,
        cursor_field: str, items_path: str, id_field: str, content_field: str,
        title_field: str, url_field: str, ctx: SourceContext,
    ) -> AsyncIterator[RawDocument]:
        cursor: str | None = None
        while True:
            p = {**params, **({"cursor": cursor} if cursor else {})}
            data, _ = await self._request_json(client, method, url, p)
            items = _get_nested(data, items_path) if items_path else data
            if not isinstance(items, list) or not items:
                break
            for item in items:
                doc = self._item_to_doc(item, id_field, content_field, title_field, url_field, ctx)
                if doc:
                    yield doc
            cursor = _get_nested(data, cursor_field) if cursor_field else None
            if not cursor:
                break

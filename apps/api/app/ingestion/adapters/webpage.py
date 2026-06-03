"""Webpage crawler source adapter.

Fetches a start URL and follows internal links up to a configurable depth,
yielding one RawDocument per page. Content is extracted from a CSS selector
and normalised as HTML by the shared normaliser.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, ClassVar
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.ingestion.adapters._http import build_client
from app.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_DEFAULT_SELECTOR = "main, article, [role=main], body"


class WebpageAdapter:
    """Adapter that crawls a website up to a configurable depth (FR-IN-x)."""

    handles: ClassVar[tuple[str, ...]] = ("webpage",)

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the adapter.

        Args:
            settings: Application settings; resolved from configuration if omitted.
        """
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """BFS-crawl from config.url up to config.max_depth.

        Args:
            ctx: Source context; ``config.url`` must be set.

        Yields:
            RawDocument: One document per successfully fetched page.

        Raises:
            SourceFetchError: If ``config.url`` is missing.
        """
        config = ctx.config
        start_url: str = config.get("url", "")
        if not start_url:
            raise SourceFetchError("webpage source requires config.url")

        max_depth: int = int(config.get("max_depth", 2))
        selector: str = config.get("selector", _DEFAULT_SELECTOR)
        url_filter_pattern: str | None = config.get("url_filter")

        parsed_start = urlparse(start_url)
        default_filter = (
            rf"^{re.escape(parsed_start.scheme)}://{re.escape(parsed_start.netloc)}(/|$)"
        )
        url_filter = re.compile(url_filter_pattern or default_filter)

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])

        async with build_client(self._settings) as client:
            while queue:
                url, depth = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)

                try:
                    response = await client.get(url)
                except Exception:
                    continue  # non-fatal: skip unreachable pages

                if response.status_code != 200:
                    continue

                html = response.text
                soup = BeautifulSoup(html, "lxml")

                content_el = soup.select_one(selector)
                content = (
                    content_el.get_text(separator="\n", strip=True) if content_el else ""
                )
                if not content.strip():
                    content = soup.get_text(separator="\n", strip=True)

                title_el = soup.find("title")
                title = title_el.get_text(strip=True) if title_el else url

                yield RawDocument(
                    external_id=url,
                    title=title,
                    doc_type="webpage",
                    content=html,
                    content_type="html",
                    source_url=url,
                    metadata={"depth": depth, "plugin_slug": ctx.plugin_slug},
                )

                if depth < max_depth:
                    for tag in soup.find_all("a", href=True):
                        href: str = tag["href"]
                        abs_url = urljoin(url, href).split("#")[0]
                        if abs_url not in visited and url_filter.match(abs_url):
                            queue.append((abs_url, depth + 1))

                await asyncio.sleep(self._settings.ingest_polite_delay_seconds)

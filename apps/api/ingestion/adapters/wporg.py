"""WordPress.org source adapter.

Fetches plugin FAQ and changelog from the WordPress.org Plugin API (FR-IN-3) and
resolved support-forum threads via polite, rate-limited HTML retrieval (FR-IN-4).
Support threads are reduced to a question plus the resolved reply. The Plugin API
returns HTML section bodies, carried through verbatim for the normaliser to clean
and sanitise (NFR-SC-4).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from html.parser import HTMLParser
from typing import Any, ClassVar

from apps.api.config import Settings, get_settings
from apps.api.ingestion.adapters._http import build_client, request_with_backoff
from apps.api.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_TOPIC_HREF = re.compile(r'href="(https://wordpress\.org/support/topic/[^"#?]+)/?"')


class WporgAdapter:
    """Adapter for WordPress.org plugin docs and support threads (FR-IN-3/4)."""

    handles: ClassVar[tuple[str, ...]] = ("wporg_faq", "wporg_changelog", "wporg_support")

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the adapter.

        Args:
            settings: Application settings; resolved from configuration if omitted.
        """
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Fetch documents for the requested WordPress.org source type.

        Args:
            ctx: Source context; ``wporg_slug`` must be set.

        Yields:
            RawDocument: A FAQ/changelog section, or one document per thread.

        Raises:
            SourceFetchError: If the slug is unset or the upstream fails.
        """
        if not ctx.wporg_slug:
            raise SourceFetchError("wporg_slug is required for WordPress.org sources")
        if ctx.source_type in ("wporg_faq", "wporg_changelog"):
            async for doc in self._fetch_plugin_section(ctx):
                yield doc
        elif ctx.source_type == "wporg_support":
            async for doc in self._fetch_support_threads(ctx):
                yield doc
        else:  # pragma: no cover - guarded by registry/handles
            raise SourceFetchError(f"unsupported source_type: {ctx.source_type}")

    async def _fetch_plugin_section(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Yield the FAQ or changelog section from the Plugin API (FR-IN-3)."""
        slug = ctx.wporg_slug
        if slug is None:
            raise SourceFetchError("wporg_slug is required for WordPress.org sources")
        api = self._settings.wporg_api_url.rstrip("/")
        url = f"{api}/plugins/info/1.2/"
        section = "faq" if ctx.source_type == "wporg_faq" else "changelog"
        async with build_client(self._settings) as client:
            response = await request_with_backoff(
                client,
                "GET",
                url,
                settings=self._settings,
                etags=ctx.etags,
                accept="application/json",
                params={"action": "plugin_information", "request[slug]": slug},
            )
            if response.status_code != 200:
                raise SourceFetchError(f"plugin API returned {response.status_code}")
            payload: dict[str, Any] = response.json()

        sections = payload.get("sections") or {}
        body = sections.get(section)
        if not body:
            return
        anchor = "faq" if section == "faq" else "developers"
        yield RawDocument(
            external_id=f"{slug}:{section}",
            title=f"{payload.get('name', slug)} — {section.upper()}",
            doc_type=ctx.source_type,
            content=str(body),
            content_type="html",
            source_url=f"{self._settings.wporg_site_url}/plugins/{slug}/#{anchor}",
            version=str(payload.get("version")) if payload.get("version") else None,
        )

    async def _fetch_support_threads(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Yield resolved support threads as question + resolved reply (FR-IN-4)."""
        max_threads = int(ctx.config.get("max_threads", 20))
        explicit = ctx.config.get("threads")
        async with build_client(self._settings) as client:
            if isinstance(explicit, list) and explicit:
                topic_urls = [str(url) for url in explicit][:max_threads]
            else:
                topic_urls = await self._discover_topics(client, ctx, max_threads)

            for index, topic_url in enumerate(topic_urls):
                if index:
                    await asyncio.sleep(self._settings.ingest_polite_delay_seconds)
                doc = await self._fetch_thread(client, ctx, topic_url)
                if doc is not None:
                    yield doc

    async def _discover_topics(self, client: Any, ctx: SourceContext, limit: int) -> list[str]:
        """Discover resolved topic URLs from the plugin support listing.

        Args:
            client: The async HTTP client.
            ctx: Source context.
            limit: Maximum number of topics to return.

        Returns:
            list[str]: Distinct topic URLs, capped at ``limit``.
        """
        site = self._settings.wporg_site_url.rstrip("/")
        url = f"{site}/support/plugin/{ctx.wporg_slug}/"
        response = await request_with_backoff(
            client, "GET", url, settings=self._settings, etags=ctx.etags, accept="text/html"
        )
        if response.status_code != 200:
            return []
        seen: list[str] = []
        for match in _TOPIC_HREF.finditer(response.text):
            topic = match.group(1)
            if topic not in seen:
                seen.append(topic)
            if len(seen) >= limit:
                break
        return seen

    async def _fetch_thread(
        self, client: Any, ctx: SourceContext, topic_url: str
    ) -> RawDocument | None:
        """Fetch one thread and reduce it to question + resolved reply (FR-IN-4).

        Args:
            client: The async HTTP client.
            ctx: Source context.
            topic_url: URL of the support topic.

        Returns:
            RawDocument | None: The reduced thread, or ``None`` if unresolved/empty.
        """
        response = await request_with_backoff(
            client, "GET", topic_url, settings=self._settings, etags=ctx.etags, accept="text/html"
        )
        if response.status_code != 200:
            return None
        parser = _ThreadParser()
        parser.feed(response.text)
        parser.close()
        if not parser.resolved or not parser.posts:
            return None
        question = parser.posts[0]
        reply = parser.posts[1] if len(parser.posts) > 1 else ""
        content = f"<p>{question}</p>" if not reply else f"<p>{question}</p><p>{reply}</p>"
        topic_id = topic_url.rstrip("/").rsplit("/", 1)[-1]
        return RawDocument(
            external_id=f"thread-{topic_id}",
            title=parser.title or topic_id,
            doc_type="wporg_support",
            content=content,
            content_type="html",
            source_url=topic_url,
            metadata={"resolved": True},
        )


class _ThreadParser(HTMLParser):
    """Extract a bbPress thread's title, resolution state, and post bodies."""

    def __init__(self) -> None:
        """Initialise the thread parser."""
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.resolved: bool = False
        self.posts: list[str] = []
        self._in_title = False
        self._capture_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Detect title elements, resolved markers, and post content blocks."""
        attr = {key: (value or "") for key, value in attrs}
        classes = attr.get("class", "")
        if "resolved" in classes:
            self.resolved = True
        if tag in {"h1", "title"} and not self.title:
            self._in_title = True
            self._parts = []
        elif "bbp-topic-content" in classes or "bbp-reply-content" in classes:
            self._capture_depth = 1
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        """Finalise the title or the current post body."""
        if self._in_title and tag in {"h1", "title"}:
            self.title = "".join(self._parts).strip()
            self._in_title = False
        elif self._capture_depth:
            text = "".join(self._parts).strip()
            if text:
                self.posts.append(text)
            self._capture_depth = 0
            self._parts = []

    def handle_data(self, data: str) -> None:
        """Capture text into the active title or post body."""
        if self._in_title or self._capture_depth:
            self._parts.append(data)

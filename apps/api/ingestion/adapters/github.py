"""GitHub source adapter.

Fetches README, CHANGELOG, ``docs/`` Markdown, and label/state-filtered issues
from a GitHub repository via the REST API (FR-IN-1/2). Requests use conditional
ETags and bounded backoff that honours rate-limit headers (FR-IN-8). Issues are
reduced to a single Q/A document: the issue body plus the first maintainer
comment treated as the accepted answer.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Sequence
from typing import Any, ClassVar

from apps.api.config import Settings, get_settings
from apps.api.ingestion.adapters._http import build_client, request_with_backoff
from apps.api.ingestion.adapters.base import RawDocument, SourceContext, SourceFetchError

_GITHUB_ACCEPT = "application/vnd.github+json"
_MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
_CHANGELOG_CANDIDATES = ("CHANGELOG.md", "CHANGELOG.txt", "CHANGELOG", "changelog.md")


class GitHubAdapter:
    """Adapter for GitHub documentation and issues (FR-IN-1/2)."""

    handles: ClassVar[tuple[str, ...]] = (
        "github_readme",
        "github_changelog",
        "github_docs",
        "github_issues",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialise the adapter.

        Args:
            settings: Application settings; resolved from configuration if omitted.
        """
        self._settings = settings or get_settings()

    async def fetch(self, ctx: SourceContext) -> AsyncIterator[RawDocument]:
        """Fetch documents for the requested GitHub source type.

        Args:
            ctx: Source context; ``github_repo`` must be set.

        Yields:
            RawDocument: One per README, changelog, docs file, or issue Q/A.

        Raises:
            SourceFetchError: If the repository is unset or the upstream fails.
        """
        if not ctx.github_repo:
            raise SourceFetchError("github_repo is required for GitHub sources")
        api = self._settings.github_api_url.rstrip("/")
        async with build_client(self._settings) as client:
            if ctx.source_type == "github_readme":
                async for doc in self._fetch_readme(client, api, ctx):
                    yield doc
            elif ctx.source_type == "github_changelog":
                async for doc in self._fetch_changelog(client, api, ctx):
                    yield doc
            elif ctx.source_type == "github_docs":
                async for doc in self._fetch_docs(client, api, ctx):
                    yield doc
            elif ctx.source_type == "github_issues":
                async for doc in self._fetch_issues(client, api, ctx):
                    yield doc
            else:  # pragma: no cover - guarded by registry/handles
                raise SourceFetchError(f"unsupported source_type: {ctx.source_type}")

    async def _get_json(self, client: Any, url: str, ctx: SourceContext) -> Any:
        """Fetch and decode a JSON response with backoff and ETag support.

        Args:
            client: The async HTTP client.
            url: Absolute API URL.
            ctx: Source context (carries the ETag store).

        Returns:
            Any: Parsed JSON, or ``None`` on 304/404.

        Raises:
            SourceFetchError: On an unexpected non-success status.
        """
        response = await request_with_backoff(
            client, "GET", url, settings=self._settings, etags=ctx.etags, accept=_GITHUB_ACCEPT
        )
        if response.status_code in (304, 404):
            return None
        if response.status_code != 200:
            raise SourceFetchError(f"GET {url} returned {response.status_code}")
        return response.json()

    @staticmethod
    def _decode_content(payload: dict[str, Any]) -> str:
        """Decode the base64 ``content`` field of a contents API payload.

        Args:
            payload: A GitHub contents API object.

        Returns:
            str: The decoded UTF-8 text.
        """
        raw = payload.get("content", "")
        return base64.b64decode(raw).decode("utf-8", errors="replace")

    async def _fetch_readme(
        self, client: Any, api: str, ctx: SourceContext
    ) -> AsyncIterator[RawDocument]:
        """Yield the repository README (FR-IN-1)."""
        payload = await self._get_json(client, f"{api}/repos/{ctx.github_repo}/readme", ctx)
        if not payload:
            return
        yield RawDocument(
            external_id=payload.get("path", "README.md"),
            title="README",
            doc_type="github_readme",
            content=self._decode_content(payload),
            content_type="markdown",
            source_url=payload.get("html_url", f"https://github.com/{ctx.github_repo}"),
        )

    async def _fetch_changelog(
        self, client: Any, api: str, ctx: SourceContext
    ) -> AsyncIterator[RawDocument]:
        """Yield the first changelog file found (FR-IN-1)."""
        for name in _CHANGELOG_CANDIDATES:
            payload = await self._get_json(
                client, f"{api}/repos/{ctx.github_repo}/contents/{name}", ctx
            )
            if payload:
                yield RawDocument(
                    external_id=payload.get("path", name),
                    title="CHANGELOG",
                    doc_type="github_changelog",
                    content=self._decode_content(payload),
                    content_type="markdown",
                    source_url=payload.get("html_url", f"https://github.com/{ctx.github_repo}"),
                )
                return

    async def _fetch_docs(
        self, client: Any, api: str, ctx: SourceContext
    ) -> AsyncIterator[RawDocument]:
        """Yield every Markdown file under the configured docs path (FR-IN-1)."""
        path = str(ctx.config.get("path", "docs")).strip("/")
        listing = await self._get_json(
            client, f"{api}/repos/{ctx.github_repo}/contents/{path}", ctx
        )
        if not isinstance(listing, list):
            return
        for entry in listing:
            name = str(entry.get("name", ""))
            if entry.get("type") != "file" or not name.lower().endswith((".md", ".markdown")):
                continue
            payload = await self._get_json(client, str(entry["url"]), ctx)
            if not payload:
                continue
            yield RawDocument(
                external_id=payload.get("path", f"{path}/{name}"),
                title=name,
                doc_type="github_docs",
                content=self._decode_content(payload),
                content_type="markdown",
                source_url=payload.get("html_url", f"https://github.com/{ctx.github_repo}"),
            )

    async def _fetch_issues(
        self, client: Any, api: str, ctx: SourceContext
    ) -> AsyncIterator[RawDocument]:
        """Yield each filtered issue as one Q/A document (FR-IN-2)."""
        labels = ctx.config.get("labels", [])
        params: dict[str, str] = {
            "state": str(ctx.config.get("state", "closed")),
            "per_page": str(ctx.config.get("per_page", 50)),
        }
        if isinstance(labels, Sequence) and not isinstance(labels, str) and labels:
            params["labels"] = ",".join(str(label) for label in labels)

        response = await request_with_backoff(
            client,
            "GET",
            f"{api}/repos/{ctx.github_repo}/issues",
            settings=self._settings,
            etags=ctx.etags,
            accept=_GITHUB_ACCEPT,
            params=params,
        )
        if response.status_code in (304, 404):
            return
        if response.status_code != 200:
            raise SourceFetchError(f"GET issues returned {response.status_code}")
        rows = response.json()
        if not isinstance(rows, list):
            return
        for issue in rows:
            if "pull_request" in issue:
                continue
            number = issue["number"]
            answer = await self._accepted_answer(client, api, ctx, int(number))
            body = str(issue.get("body") or "").strip()
            content = body if not answer else f"{body}\n\nAccepted answer:\n{answer}"
            yield RawDocument(
                external_id=f"issue-{number}",
                title=str(issue.get("title", f"Issue #{number}")),
                doc_type="github_issues",
                content=content,
                content_type="markdown",
                source_url=str(issue.get("html_url", "")),
                metadata={
                    "state": issue.get("state"),
                    "labels": [label.get("name") for label in issue.get("labels", [])],
                    "has_accepted_answer": answer is not None,
                },
            )

    async def _accepted_answer(
        self, client: Any, api: str, ctx: SourceContext, number: int
    ) -> str | None:
        """Return the first maintainer comment for an issue, if any (FR-IN-2).

        Args:
            client: The async HTTP client.
            api: GitHub API base URL.
            ctx: Source context.
            number: Issue number.

        Returns:
            str | None: The accepted-answer comment body, or ``None``.
        """
        comments = await self._get_json(
            client, f"{api}/repos/{ctx.github_repo}/issues/{number}/comments", ctx
        )
        if not isinstance(comments, list):
            return None
        for comment in comments:
            if comment.get("author_association") in _MAINTAINER_ASSOCIATIONS:
                text = str(comment.get("body") or "").strip()
                if text:
                    return text
        return None

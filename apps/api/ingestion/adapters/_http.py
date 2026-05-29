"""Shared async HTTP utilities for source adapters.

Builds configured ``httpx`` clients and performs requests with bounded
exponential backoff that honours ``Retry-After`` and GitHub rate-limit headers
(FR-IN-8). Conditional requests via ``If-None-Match`` are supported by passing a
mutable ETag store; a ``304 Not Modified`` is returned to the caller unchanged.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, MutableMapping

import httpx

from apps.api.config import Settings
from apps.api.ingestion.adapters.base import SourceFetchError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS = 60.0


def build_client(
    settings: Settings, *, base_url: str = "", headers: Mapping[str, str] | None = None
) -> httpx.AsyncClient:
    """Construct a configured async HTTP client.

    Args:
        settings: Application settings supplying timeout and User-Agent.
        base_url: Optional base URL for relative request paths.
        headers: Optional default headers merged with the User-Agent.

    Returns:
        httpx.AsyncClient: A client with timeout, User-Agent, and follow-redirects set.
    """
    default_headers = {"User-Agent": settings.http_user_agent}
    if headers:
        default_headers.update(headers)
    return httpx.AsyncClient(
        base_url=base_url,
        headers=default_headers,
        timeout=settings.http_timeout_seconds,
        follow_redirects=True,
    )


def _retry_after_seconds(response: httpx.Response, attempt: int) -> float:
    """Compute the delay before the next attempt.

    Honours an explicit ``Retry-After`` header (seconds) and the GitHub
    ``X-RateLimit-Reset`` epoch when present; otherwise uses capped exponential
    backoff.

    Args:
        response: The response that triggered a retry.
        attempt: Zero-based attempt number that just failed.

    Returns:
        float: Seconds to wait, capped at one minute.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), _MAX_BACKOFF_SECONDS)
    return min(2.0**attempt, _MAX_BACKOFF_SECONDS)


def _is_rate_limited(response: httpx.Response) -> bool:
    """Report whether a 403 is a GitHub rate-limit rejection.

    Args:
        response: The 403 response to inspect.

    Returns:
        bool: ``True`` if the remaining rate-limit quota is exhausted.
    """
    return bool(response.headers.get("X-RateLimit-Remaining") == "0")


async def request_with_backoff(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    settings: Settings,
    etags: MutableMapping[str, str] | None = None,
    accept: str | None = None,
    params: Mapping[str, str] | None = None,
) -> httpx.Response:
    """Perform an HTTP request with bounded retry and conditional support.

    Retries transient failures (429/5xx and rate-limited 403s) up to the
    configured ceiling, waiting per :func:`_retry_after_seconds`. When an ETag is
    known for ``url`` it is sent as ``If-None-Match``; a fresh ETag on a 200 is
    recorded back into ``etags``.

    Args:
        client: The async client to use.
        method: HTTP method.
        url: Absolute or base-relative URL.
        settings: Application settings (retry ceiling).
        etags: Optional mutable ETag store keyed by URL (FR-IN-8).
        accept: Optional ``Accept`` header value.
        params: Optional query parameters.

    Returns:
        httpx.Response: The final response (which may be ``304 Not Modified``).

    Raises:
        SourceFetchError: On a non-retryable error or after exhausting retries.
    """
    headers: dict[str, str] = {}
    if accept:
        headers["Accept"] = accept
    if settings.github_token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {settings.github_token.get_secret_value()}"
    if etags is not None and url in etags:
        headers["If-None-Match"] = etags[url]

    last_status = 0
    for attempt in range(settings.http_max_retries + 1):
        try:
            response = await client.request(method, url, headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"{method} {url} failed: {exc}") from exc

        last_status = response.status_code
        if response.status_code in _RETRYABLE_STATUS or (
            response.status_code == 403 and _is_rate_limited(response)
        ):
            if attempt >= settings.http_max_retries:
                break
            delay = _retry_after_seconds(response, attempt)
            logger.warning(
                "retrying request after transient failure",
                extra={"url": url, "status": response.status_code, "delay_s": delay},
            )
            await asyncio.sleep(delay)
            continue

        if etags is not None and response.status_code == 200 and "ETag" in response.headers:
            etags[url] = response.headers["ETag"]
        return response

    raise SourceFetchError(f"{method} {url} failed after retries (last status {last_status})")

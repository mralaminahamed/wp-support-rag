"""FastAPI dependencies.

Provides request-scoped access to the database session, Redis, settings, the
embedding client, and the LLM provider, plus a per-IP rate limiter (NFR-SC-2)
and bearer-token admin authentication (FR-DL-4). The embedding-client and
provider dependencies are overridable in tests via ``app.dependency_overrides``.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import hashlib

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis

from apps.api.config import Settings, get_settings
from apps.api.db.redis import get_redis
from apps.api.llm.base import LLMProvider
from apps.api.llm.factory import build_provider
from apps.api.processing.embedder import EmbeddingClient, build_embedding_client


def get_settings_dep() -> Settings:
    """Return application settings.

    Returns:
        Settings: The process settings.
    """
    return get_settings()


def get_redis_dep() -> Redis:
    """Return the shared async Redis client.

    Returns:
        Redis: The Redis client.
    """
    return get_redis()


def get_embedding_client() -> EmbeddingClient:
    """Return the configured embedding client (overridable in tests).

    Returns:
        EmbeddingClient: The embedding client.
    """
    return build_embedding_client(get_settings())


def get_provider() -> LLMProvider:
    """Return the configured LLM provider (overridable in tests).

    Returns:
        LLMProvider: The provider.
    """
    return build_provider(get_settings())


def hash_ip(ip: str) -> str:
    """Return a truncated, hashed IP for rate limiting only (NFR-SC-5).

    Args:
        ip: The caller IP address.

    Returns:
        str: A 16-hex-char truncated SHA-256 digest of the IP.
    """
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


async def rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Enforce a per-IP request budget over a sliding window (NFR-SC-2).

    Args:
        request: The incoming request (for the client IP).
        redis: The Redis client backing the counter.
        settings: Settings supplying the window and limit.

    Returns:
        str: The hashed client IP (reused for query logging).

    Raises:
        HTTPException: 429 when the per-IP request budget is exceeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hash_ip(client_ip)
    key = f"ratelimit:{ip_hash}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.rate_limit_window_seconds)
    if count > settings.rate_limit_max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded"
        )
    return ip_hash


async def require_admin(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Require a valid admin bearer token (FR-DL-4, NFR-SC-2).

    Args:
        authorization: The ``Authorization`` header value.
        settings: Settings holding the configured admin token.

    Raises:
        HTTPException: 401 when the token is missing, misconfigured, or invalid.
    """
    if settings.admin_bearer_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="admin auth not configured"
        )
    expected = f"Bearer {settings.admin_bearer_token.get_secret_value()}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

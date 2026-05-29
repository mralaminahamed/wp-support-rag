"""Per-plugin centroid embeddings.

Computes the mean of a plugin's chunk vectors and caches it in Redis for
slug-less query routing (ADR-004, used in Phase 4). The mean is computed in
Postgres via pgvector's ``avg`` aggregate and refreshed whenever a plugin's
index changes materially (after chunks are written).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import json
import logging
import uuid

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

logger = logging.getLogger(__name__)


def centroid_key(plugin_id: uuid.UUID) -> str:
    """Return the Redis key holding a plugin's centroid.

    Args:
        plugin_id: The plugin id.

    Returns:
        str: The Redis key.
    """
    return f"centroid:{plugin_id}"


async def refresh_plugin_centroid(
    session: AsyncSession,
    redis: Redis,
    plugin_id: uuid.UUID,
    settings: Settings,
) -> list[float] | None:
    """Recompute and cache a plugin's centroid embedding (ADR-004).

    Args:
        session: Active async session.
        redis: Async Redis client.
        plugin_id: The plugin whose centroid to refresh.
        settings: Application settings (centroid TTL).

    Returns:
        list[float] | None: The cached centroid, or ``None`` if the plugin has
        no chunks (in which case any stale centroid is removed).
    """
    row = (
        await session.execute(
            text("SELECT avg(embedding)::text AS centroid FROM chunks WHERE plugin_id = :pid"),
            {"pid": str(plugin_id)},
        )
    ).first()
    key = centroid_key(plugin_id)
    if row is None or row.centroid is None:
        await redis.delete(key)
        return None
    vector: list[float] = json.loads(row.centroid)
    await redis.set(key, json.dumps(vector), ex=settings.centroid_cache_ttl_seconds)
    logger.info(
        "refreshed plugin centroid", extra={"plugin_id": str(plugin_id), "dims": len(vector)}
    )
    return vector


async def get_plugin_centroid(redis: Redis, plugin_id: uuid.UUID) -> list[float] | None:
    """Return a plugin's cached centroid, if present.

    Args:
        redis: Async Redis client.
        plugin_id: The plugin id.

    Returns:
        list[float] | None: The centroid vector, or ``None`` if not cached.
    """
    cached = await redis.get(centroid_key(plugin_id))
    if cached is None:
        return None
    result: list[float] = json.loads(cached)
    return result

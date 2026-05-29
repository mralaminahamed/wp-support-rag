"""Centroid-based plugin routing (ADR-004, FR-QR-2).

When a query arrives without a ``plugin_slug``, route it to the most likely
plugin(s) by comparing the query embedding against cached per-plugin centroids
(means of each plugin's chunk vectors). This avoids an extra LLM classification
call; the top one or two plugins by cosine similarity scope retrieval.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import math
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import Plugin
from app.processing.centroid import get_plugin_centroid


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return the cosine similarity of two equal-length vectors.

    Args:
        a: First vector.
        b: Second vector.

    Returns:
        float: Cosine similarity in [-1, 1]; 0.0 if either vector is zero or
        the lengths differ.
    """
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def route_query(
    session: AsyncSession,
    redis: Redis,
    embedding: list[float],
    settings: Settings | None = None,
) -> list[uuid.UUID]:
    """Route a slug-less query to the most similar plugin(s) (FR-QR-2).

    Compares the query embedding against each active plugin's cached centroid and
    returns up to ``route_max_plugins`` plugin ids by descending cosine similarity.
    Plugins without a cached centroid are skipped.

    Args:
        session: Active async session.
        redis: Async Redis client holding the centroids.
        embedding: The query embedding vector.
        settings: Application settings; resolved from configuration if omitted.

    Returns:
        list[uuid.UUID]: Routed plugin ids, best first (possibly empty).
    """
    settings = settings or get_settings()
    plugin_ids = (
        (await session.execute(select(Plugin.id).where(Plugin.status == "active"))).scalars().all()
    )

    scored: list[tuple[float, uuid.UUID]] = []
    for plugin_id in plugin_ids:
        centroid = await get_plugin_centroid(redis, plugin_id)
        if centroid is None:
            continue
        scored.append((cosine_similarity(embedding, centroid), plugin_id))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [plugin_id for _score, plugin_id in scored[: settings.route_max_plugins]]

"""Admin endpoints (FR-DL-4, FR-FB-3, FR-IN-6).

Bearer-authenticated endpoints to register a plugin, trigger ingestion, and read
aggregate operational metrics. Ingestion is dispatched as one Celery task per
enabled source so a failing source never blocks its siblings (FR-IN-7).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.api.schemas import IngestTriggerResponse, MetricsResponse, PluginRegistration
from app.db.engine import get_session
from app.db.models import Feedback, Query
from app.ingestion.registry import (
    PluginSpec,
    SourceSpec,
    get_plugin_by_slug,
    list_sources,
    load_plugin_spec,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def _percentile(values: list[int], pct: float) -> int:
    """Return the nearest-rank percentile of a list of ints.

    Args:
        values: The samples.
        pct: Percentile in [0, 1].

    Returns:
        int: The percentile value, or 0 if there are no samples.
    """
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(pct * len(ordered)) - 1))
    return ordered[rank]


@router.post("/plugins", status_code=status.HTTP_201_CREATED)
async def register_plugin(
    payload: PluginRegistration, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Register or reconcile a plugin and its sources (FR-PM-1/2).

    Args:
        payload: The plugin registration.
        session: Database session.

    Returns:
        dict[str, str]: The persisted plugin slug and id.
    """
    spec = PluginSpec(
        slug=payload.slug,
        name=payload.name,
        wporg_slug=payload.wporg_slug,
        github_repo=payload.github_repo,
        sources=[SourceSpec.model_validate({"source_type": st}) for st in payload.source_types],
    )
    plugin = await load_plugin_spec(session, spec)
    await session.commit()
    return {"slug": plugin.slug, "id": str(plugin.id)}


@router.post("/ingest/{plugin_slug}", response_model=IngestTriggerResponse)
async def trigger_ingest(
    plugin_slug: str, session: AsyncSession = Depends(get_session)
) -> IngestTriggerResponse:
    """Dispatch ingestion for every enabled source of a plugin (FR-IN-6/7).

    Args:
        plugin_slug: The plugin to ingest.
        session: Database session.

    Returns:
        IngestTriggerResponse: The slug and number of sources enqueued.

    Raises:
        HTTPException: 404 if the plugin is unknown.
    """
    from app.ingestion.tasks import ingest_source_task

    plugin = await get_plugin_by_slug(session, plugin_slug)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plugin not found")
    sources = await list_sources(session, plugin.id, enabled_only=True)
    for source in sources:
        ingest_source_task.delay(str(source.id))
    return IngestTriggerResponse(plugin_slug=plugin_slug, enqueued_sources=len(sources))


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(session: AsyncSession = Depends(get_session)) -> MetricsResponse:
    """Return aggregate operational metrics (FR-FB-3).

    Args:
        session: Database session.

    Returns:
        MetricsResponse: Deflection, helpful, cache-hit, degraded rates, mean
        cost, and p95 latency.
    """
    total = (await session.execute(select(func.count()).select_from(Query))).scalar_one()
    if total == 0:
        return MetricsResponse(
            total_queries=0,
            deflection_rate=0.0,
            helpful_rate=0.0,
            cache_hit_rate=0.0,
            degraded_rate=0.0,
            mean_cost_usd=0.0,
            p95_latency_ms=0,
        )

    cached = (
        await session.execute(select(func.count()).where(Query.cached.is_(True)))
    ).scalar_one()
    degraded = (
        await session.execute(select(func.count()).where(Query.degraded.is_(True)))
    ).scalar_one()
    mean_cost = (await session.execute(select(func.avg(Query.cost_usd)))).scalar_one()
    latencies = [
        int(value)
        for value in (await session.execute(select(Query.latency_ms))).scalars().all()
        if value is not None
    ]
    feedback_total = (
        await session.execute(select(func.count()).select_from(Feedback))
    ).scalar_one()
    helpful = (
        await session.execute(select(func.count()).where(Feedback.rating == "helpful"))
    ).scalar_one()

    return MetricsResponse(
        total_queries=total,
        deflection_rate=(total - degraded) / total,
        helpful_rate=(helpful / feedback_total) if feedback_total else 0.0,
        cache_hit_rate=cached / total,
        degraded_rate=degraded / total,
        mean_cost_usd=float(mean_cost) if mean_cost is not None else 0.0,
        p95_latency_ms=_percentile(latencies, 0.95),
    )

"""Admin endpoints (FR-DL-4, FR-FB-3, FR-IN-6).

Bearer-authenticated endpoints to register a plugin, trigger ingestion, and read
aggregate operational metrics. Ingestion is dispatched as one Celery task per
enabled source so a failing source never blocks its siblings (FR-IN-7).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_redis_dep, get_settings_dep, require_admin
from app.api.schemas import (
    IngestAllResponse,
    IngestTriggerResponse,
    LLMConfigResponse,
    LLMConfigUpdate,
    LLMProviderInfo,
    MetricsResponse,
    PluginRegistration,
    PluginSummary,
    SourceSummary,
)
from app.config import ProviderName, Settings
from app.db.engine import get_session
from app.db.models import Feedback, Query
from app.ingestion.registry import (
    PluginSpec,
    SourceSpec,
    get_plugin_by_slug,
    list_plugins,
    list_sources,
    load_plugin_spec,
)
from app.llm.runtime import (
    PROVIDERS,
    clear_override,
    env_model,
    is_configured,
    resolve,
    set_override,
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


async def _llm_config(redis: Redis, settings: Settings) -> LLMConfigResponse:
    """Assemble the LLM-config response from the effective selection.

    Args:
        redis: Redis client backing the runtime override.
        settings: Application settings supplying the env defaults.

    Returns:
        LLMConfigResponse: Active provider/model plus all selectable providers.
    """
    effective = await resolve(redis, settings)
    return LLMConfigResponse(
        provider=effective.provider,
        model=effective.model,
        source=effective.source,
        default_provider=settings.default_provider,
        providers=[
            LLMProviderInfo(
                name=name,
                default_model=env_model(settings, name),
                configured=is_configured(settings, name),
            )
            for name in PROVIDERS
        ],
    )


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config(
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
) -> LLMConfigResponse:
    """Return the active generation provider/model and the choices (FR-GN-3).

    Args:
        redis: Redis client backing the runtime override.
        settings: Application settings.

    Returns:
        LLMConfigResponse: The effective configuration.
    """
    return await _llm_config(redis, settings)


@router.put("/llm", response_model=LLMConfigResponse)
async def set_llm_config(
    payload: LLMConfigUpdate,
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
) -> LLMConfigResponse:
    """Override the active generation provider/model at runtime (FR-GN-3).

    The model is optional and defaults to the provider's env-configured model.
    The override is stored in Redis and applied to subsequent generations
    without a restart.

    Args:
        payload: The provider and optional model to activate.
        redis: Redis client backing the runtime override.
        settings: Application settings.

    Returns:
        LLMConfigResponse: The new effective configuration.

    Raises:
        HTTPException: 422 if the provider is unknown.
    """
    if payload.provider not in PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown provider: {payload.provider}",
        )
    provider: ProviderName = payload.provider
    model = (payload.model or "").strip() or env_model(settings, provider)
    await set_override(redis, provider, model)
    return await _llm_config(redis, settings)


@router.delete("/llm", response_model=LLMConfigResponse)
async def reset_llm_config(
    redis: Redis = Depends(get_redis_dep),
    settings: Settings = Depends(get_settings_dep),
) -> LLMConfigResponse:
    """Clear any override and revert to the env-file defaults (FR-GN-3).

    Args:
        redis: Redis client backing the runtime override.
        settings: Application settings.

    Returns:
        LLMConfigResponse: The configuration after reverting to env defaults.
    """
    await clear_override(redis)
    return await _llm_config(redis, settings)


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


@router.get("/plugins", response_model=list[PluginSummary])
async def list_registered_plugins(
    session: AsyncSession = Depends(get_session),
) -> list[PluginSummary]:
    """List registered plugins with their source counts (FR-PM-1).

    Args:
        session: Database session.

    Returns:
        list[PluginSummary]: One summary per plugin.
    """
    plugins = await list_plugins(session)
    summaries: list[PluginSummary] = []
    for plugin in plugins:
        sources = await list_sources(session, plugin.id)
        summaries.append(
            PluginSummary(
                slug=plugin.slug,
                name=plugin.name,
                status=plugin.status,
                wporg_slug=plugin.wporg_slug,
                github_repo=plugin.github_repo,
                source_count=len(sources),
            )
        )
    return summaries


@router.get("/plugins/{plugin_slug}/sources", response_model=list[SourceSummary])
async def list_plugin_sources(
    plugin_slug: str, session: AsyncSession = Depends(get_session)
) -> list[SourceSummary]:
    """List a plugin's sources and their ingestion state (FR-PM-2/4).

    Args:
        plugin_slug: The plugin to inspect.
        session: Database session.

    Returns:
        list[SourceSummary]: The plugin's sources.

    Raises:
        HTTPException: 404 if the plugin is unknown.
    """
    plugin = await get_plugin_by_slug(session, plugin_slug)
    if plugin is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plugin not found")
    sources = await list_sources(session, plugin.id)
    return [
        SourceSummary(
            source_type=source.source_type,
            enabled=source.enabled,
            last_ingested_at=source.last_ingested_at.isoformat()
            if source.last_ingested_at
            else None,
        )
        for source in sources
    ]


@router.post("/ingest", response_model=IngestAllResponse)
async def trigger_ingest_all(session: AsyncSession = Depends(get_session)) -> IngestAllResponse:
    """Dispatch ingestion for every plugin's enabled sources (FR-IN-6/7).

    One Celery task is enqueued per ``(plugin, source)`` so a failing source never
    aborts the others.

    Args:
        session: Database session.

    Returns:
        IngestAllResponse: Totals and per-plugin enqueue counts.
    """
    from app.ingestion.tasks import ingest_source_task

    plugins = await list_plugins(session)
    by_plugin: list[IngestTriggerResponse] = []
    total = 0
    for plugin in plugins:
        sources = await list_sources(session, plugin.id, enabled_only=True)
        for source in sources:
            ingest_source_task.delay(str(source.id))
        by_plugin.append(
            IngestTriggerResponse(plugin_slug=plugin.slug, enqueued_sources=len(sources))
        )
        total += len(sources)
    return IngestAllResponse(plugins=len(plugins), enqueued_sources=total, by_plugin=by_plugin)


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
async def metrics(
    plugin_slug: str | None = None, session: AsyncSession = Depends(get_session)
) -> MetricsResponse:
    """Return aggregate operational metrics, optionally per plugin (FR-FB-3).

    Args:
        plugin_slug: Optional plugin filter; aggregates across all plugins when omitted.
        session: Database session.

    Returns:
        MetricsResponse: Deflection, helpful, cache-hit, degraded rates, mean
        cost, and p95 latency.

    Raises:
        HTTPException: 404 if a given plugin slug is unknown.
    """
    plugin_id = None
    if plugin_slug is not None:
        plugin = await get_plugin_by_slug(session, plugin_slug)
        if plugin is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plugin not found")
        plugin_id = plugin.id

    def scoped(stmt: Select[Any]) -> Select[Any]:
        return stmt.where(Query.plugin_id == plugin_id) if plugin_id is not None else stmt

    total = (await session.execute(scoped(select(func.count()).select_from(Query)))).scalar_one()
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
        await session.execute(scoped(select(func.count()).where(Query.cached.is_(True))))
    ).scalar_one()
    degraded = (
        await session.execute(scoped(select(func.count()).where(Query.degraded.is_(True))))
    ).scalar_one()
    mean_cost = (await session.execute(scoped(select(func.avg(Query.cost_usd))))).scalar_one()
    latencies = [
        int(value)
        for value in (await session.execute(scoped(select(Query.latency_ms)))).scalars().all()
        if value is not None
    ]
    feedback_stmt = select(func.count()).select_from(Feedback)
    helpful_stmt = select(func.count()).where(Feedback.rating == "helpful")
    if plugin_id is not None:
        feedback_stmt = feedback_stmt.join(Query, Query.id == Feedback.query_id).where(
            Query.plugin_id == plugin_id
        )
        helpful_stmt = helpful_stmt.join(Query, Query.id == Feedback.query_id).where(
            Query.plugin_id == plugin_id
        )
    feedback_total = (await session.execute(feedback_stmt)).scalar_one()
    helpful = (await session.execute(helpful_stmt)).scalar_one()

    return MetricsResponse(
        total_queries=total,
        deflection_rate=(total - degraded) / total,
        helpful_rate=(helpful / feedback_total) if feedback_total else 0.0,
        cache_hit_rate=cached / total,
        degraded_rate=degraded / total,
        mean_cost_usd=float(mean_cost) if mean_cost is not None else 0.0,
        p95_latency_ms=_percentile(latencies, 0.95),
    )

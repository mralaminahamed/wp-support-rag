"""Celery application and ingestion tasks.

Defines the configured Celery application used by the ``worker`` and ``beat``
services (broker/backend from configuration, NFR-MN-4) and the ingestion tasks.
Each ``(plugin, source)`` pair is its own task and records an ``ingestion_runs``
row; a content hash per document skips unchanged content (FR-IN-5), and a
failure in one source never aborts its siblings (FR-IN-7).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import UTC, datetime

from celery import Celery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.engine import get_sessionmaker
from app.db.models import Document, IngestionRun, Plugin, Source
from app.ingestion.adapters.base import RawDocument, SourceAdapter, SourceContext
from app.ingestion.adapters.github import GitHubAdapter
from app.ingestion.adapters.wporg import WporgAdapter
from app.ingestion.normalize import normalize
from app.ingestion.summary import IngestSummary

logger = logging.getLogger(__name__)

_settings = get_settings()
_redis_url = str(_settings.redis_dsn)

celery_app = Celery(
    "wp_support_rag",
    broker=_redis_url,
    backend=_redis_url,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
)

_GITHUB_ADAPTER = GitHubAdapter()
_WPORG_ADAPTER = WporgAdapter()
_ADAPTERS: dict[str, SourceAdapter] = {
    **dict.fromkeys(_GITHUB_ADAPTER.handles, _GITHUB_ADAPTER),
    **dict.fromkeys(_WPORG_ADAPTER.handles, _WPORG_ADAPTER),
}


def resolve_adapter(source_type: str) -> SourceAdapter:
    """Return the adapter registered for a source type.

    Args:
        source_type: The source type to resolve.

    Returns:
        SourceAdapter: The adapter handling that source type.

    Raises:
        KeyError: If no adapter handles the source type.
    """
    return _ADAPTERS[source_type]


def content_hash(text: str) -> str:
    """Return the SHA-256 hex digest of normalised document text (FR-IN-5).

    Args:
        text: Normalised document text.

    Returns:
        str: The hex digest used to detect unchanged content.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _upsert_document(session: AsyncSession, source: Source, raw: RawDocument) -> str:
    """Insert, update, or skip a document by content hash (FR-IN-5).

    Args:
        session: Active async session.
        source: The owning source.
        raw: The fetched raw document.

    Returns:
        str: One of ``"new"``, ``"updated"``, or ``"unchanged"``.
    """
    digest = content_hash(normalize(raw.content, raw.content_type).text)
    existing = (
        await session.execute(
            select(Document).where(
                Document.source_id == source.id, Document.external_id == raw.external_id
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        session.add(
            Document(
                source_id=source.id,
                plugin_id=source.plugin_id,
                external_id=raw.external_id,
                title=raw.title,
                doc_type=raw.doc_type,
                content_hash=digest,
                source_url=raw.source_url,
                version=raw.version,
            )
        )
        return "new"
    if existing.content_hash == digest:
        return "unchanged"
    existing.title = raw.title
    existing.content_hash = digest
    existing.source_url = raw.source_url
    existing.version = raw.version
    existing.fetched_at = datetime.now(UTC)
    return "updated"


async def ingest_source(
    source_id: uuid.UUID,
    *,
    adapter: SourceAdapter | None = None,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
) -> IngestSummary:
    """Ingest one source, recording a run and isolating failures (FR-IN-5/7).

    A run row is created up front. Adapter or persistence failures mark only this
    run failed and are not re-raised, so a caller iterating sibling sources
    continues unaffected (FR-IN-7).

    Args:
        source_id: The source to ingest.
        adapter: Optional adapter override (used by tests); resolved by type otherwise.
        sessionmaker: Optional session factory override; the shared one otherwise.

    Returns:
        IngestSummary: The outcome counts and status for this source.
    """
    factory = sessionmaker or get_sessionmaker()

    async with factory() as session:
        source = await session.get(Source, source_id)
        if source is None:
            return IngestSummary(
                source_id=source_id,
                source_type="",
                status="failed",
                error="source not found",
            )
        plugin = await session.get(Plugin, source.plugin_id)
        run = IngestionRun(source_id=source.id, status="running")
        session.add(run)
        await session.commit()

    new = updated = unchanged = 0
    try:
        chosen = adapter or resolve_adapter(source.source_type)
        ctx = SourceContext(
            plugin_slug=plugin.slug if plugin else source.plugin_id.hex,
            source_type=source.source_type,
            github_repo=plugin.github_repo if plugin else None,
            wporg_slug=plugin.wporg_slug if plugin else None,
            config=dict(source.config),
        )
        async with factory() as session:
            async for raw in chosen.fetch(ctx):
                outcome = await _upsert_document(session, source, raw)
                new += outcome == "new"
                updated += outcome == "updated"
                unchanged += outcome == "unchanged"
            source_row = await session.get(Source, source_id)
            if source_row is not None:
                source_row.last_ingested_at = datetime.now(UTC)
            run_row = await session.get(IngestionRun, run.id)
            if run_row is not None:
                run_row.status = "succeeded"
                run_row.finished_at = datetime.now(UTC)
                run_row.documents_processed = new + updated + unchanged
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - isolate per-source failures (FR-IN-7)
        logger.warning(
            "ingestion failed for source",
            extra={"source_id": str(source_id), "source_type": source.source_type},
            exc_info=True,
        )
        async with factory() as session:
            run_row = await session.get(IngestionRun, run.id)
            if run_row is not None:
                run_row.status = "failed"
                run_row.finished_at = datetime.now(UTC)
                run_row.error = str(exc)
            await session.commit()
        return IngestSummary(
            source_id=source_id, source_type=source.source_type, status="failed", error=str(exc)
        )

    return IngestSummary(
        source_id=source_id,
        source_type=source.source_type,
        status="succeeded",
        documents_new=new,
        documents_updated=updated,
        documents_unchanged=unchanged,
    )


async def ingest_plugin(plugin_id: uuid.UUID) -> list[IngestSummary]:
    """Ingest every enabled source of a plugin, isolating per-source failures.

    Args:
        plugin_id: The plugin whose sources to ingest.

    Returns:
        list[IngestSummary]: One summary per enabled source.
    """
    factory = get_sessionmaker()
    async with factory() as session:
        result = await session.execute(
            select(Source.id).where(Source.plugin_id == plugin_id, Source.enabled.is_(True))
        )
        source_ids = list(result.scalars().all())
    return [await ingest_source(source_id) for source_id in source_ids]


@celery_app.task(name="ingestion.ingest_source")
def ingest_source_task(source_id: str) -> dict[str, object]:
    """Celery entry point to ingest a single source (FR-IN-6).

    Args:
        source_id: String UUID of the source to ingest.

    Returns:
        dict[str, object]: The serialised :class:`IngestSummary`.
    """
    summary = asyncio.run(ingest_source(uuid.UUID(source_id)))
    return summary.model_dump(mode="json")


@celery_app.task(name="ingestion.ingest_plugin")
def ingest_plugin_task(plugin_id: str) -> list[str]:
    """Celery entry point that fans out one task per enabled source (FR-IN-7).

    Args:
        plugin_id: String UUID of the plugin to ingest.

    Returns:
        list[str]: The dispatched source ids.
    """
    factory = get_sessionmaker()

    async def _source_ids() -> list[str]:
        async with factory() as session:
            result = await session.execute(
                select(Source.id).where(
                    Source.plugin_id == uuid.UUID(plugin_id), Source.enabled.is_(True)
                )
            )
            return [str(source_id) for source_id in result.scalars().all()]

    ids = asyncio.run(_source_ids())
    for source_id in ids:
        ingest_source_task.delay(source_id)
    return ids

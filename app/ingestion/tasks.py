"""Celery application for the ingestion plane.

Defines the configured Celery application used by the ``worker`` and ``beat``
services. The broker and result backend are resolved from configuration
(NFR-MN-4) and point at Redis (architecture §1.1). Concrete ``(plugin, source)``
ingestion tasks are registered in Phase 2; this module provides the running
application so the worker and scheduler boot from ``docker compose up`` (NFR-PT-1).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from celery import Celery

from app.config import get_settings

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

"""FastAPI application factory.

Builds the ASGI application: configures structured logging, installs the
correlation-id middleware and CORS, manages startup/shutdown via lifespan, and
exposes a ``/health`` endpoint. In this phase ``/health`` reports service status
only; database and Redis probes are wired in Phase 1.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.observability.logging import CorrelationIdMiddleware, configure_logging

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health probe payload.

    Attributes:
        status: Overall service status; ``"ok"`` when the process is serving.
        service: The configured service name.
        environment: The active deployment environment.
    """

    status: str
    service: str
    environment: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown.

    On startup, resolves and stashes settings on the app state so request
    handlers share one validated configuration. Datastore engines (DB pool,
    Redis client) are attached here in Phase 1; this phase has no such resources
    to acquire or release.

    Args:
        app: The application whose lifecycle is being managed.

    Yields:
        None: Control returns to the server for the lifetime of the application.
    """
    settings: Settings = get_settings()
    app.state.settings = settings
    logger.info(
        "service starting",
        extra={"environment": settings.environment, "provider": settings.default_provider},
    )
    yield
    logger.info("service stopping")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Returns:
        FastAPI: A fully wired application instance ready to serve.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        """Report liveness of the service process.

        Datastore connectivity (PostgreSQL, Redis) is reported from Phase 1
        onward; for now a successful response means the process is up.

        Returns:
            HealthResponse: The current service status.
        """
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
        )

    return app


app = create_app()
"""Module-level ASGI application for ``uvicorn app.main:app``."""

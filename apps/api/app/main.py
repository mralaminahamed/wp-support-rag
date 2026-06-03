"""FastAPI application factory.

Builds the ASGI application: configures structured logging, installs the
correlation-id middleware and CORS, manages startup/shutdown via lifespan,
registers all routers, calls the first-boot admin bootstrap, and exposes
a /health endpoint that probes PostgreSQL and Redis connectivity.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app.api import routes_admin, routes_query
from app.api.routes_adapters import router as adapters_router
from app.api.routes_auth import router as auth_router
from app.api.routes_setup import router as setup_router
from app.api.routes_threads import router as threads_router
from app.api.routes_users import router as users_router
from app.auth.bootstrap import maybe_bootstrap_admin
from app.config import get_settings
from app.db.engine import dispose_engine, get_sessionmaker
from app.db.redis import close_redis, get_redis
from app.ingestion.adapter_registry import build_registry, init_registry
from app.observability.logging import CorrelationIdMiddleware, configure_logging

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health probe payload.

    Attributes:
        status: Overall status; ``"ok"`` when every dependency is reachable,
            otherwise ``"degraded"``.
        service: The configured service name.
        environment: The active deployment environment.
        database: Connectivity status of PostgreSQL (``"ok"`` or ``"unavailable"``).
        redis: Connectivity status of Redis (``"ok"`` or ``"unavailable"``).
    """

    status: str
    service: str
    environment: str
    database: str
    redis: str


async def _check_database() -> bool:
    """Probe PostgreSQL with a trivial query.

    Returns:
        bool: ``True`` if a connection executes ``SELECT 1`` successfully.
    """
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("database health probe failed", exc_info=True)
        return False


async def _check_redis() -> bool:
    """Probe Redis with a ``PING``.

    Returns:
        bool: ``True`` if the server responds to ``PING``.
    """
    try:
        return bool(await get_redis().ping())
    except Exception:
        logger.warning("redis health probe failed", exc_info=True)
        return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown.

    On startup, resolves settings, warms the shared engine and Redis client,
    and runs the first-boot bootstrap (seeds super_admin if no users exist).
    On shutdown, disposes the engine pool and closes the Redis client.

    Args:
        app: The application whose lifecycle is being managed.

    Yields:
        None: Control returns to the server for the lifetime of the application.
    """
    settings = get_settings()
    app.state.settings = settings
    app.state.sessionmaker = get_sessionmaker()
    app.state.redis = get_redis()
    logger.info(
        "service starting",
        extra={"environment": settings.environment, "provider": settings.default_provider},
    )
    async with get_sessionmaker()() as session:
        await maybe_bootstrap_admin(session, settings)
    registry = await build_registry(app.state.sessionmaker)
    init_registry(registry)
    try:
        yield
    finally:
        logger.info("service stopping")
        await dispose_engine()
        await close_redis()


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
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(routes_query.router)
    app.include_router(routes_admin.router)
    app.include_router(adapters_router)
    app.include_router(threads_router)
    app.include_router(setup_router)

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> JSONResponse:
        """Report service liveness and dependency connectivity.

        Probes PostgreSQL and Redis concurrently. Returns HTTP 200 when both are
        reachable and HTTP 503 when either is down.

        Returns:
            JSONResponse: The health payload with a 200 or 503 status code.
        """
        db_ok, redis_ok = await asyncio.gather(_check_database(), _check_redis())
        healthy = db_ok and redis_ok
        body = HealthResponse(
            status="ok" if healthy else "degraded",
            service=settings.app_name,
            environment=settings.environment,
            database="ok" if db_ok else "unavailable",
            redis="ok" if redis_ok else "unavailable",
        )
        return JSONResponse(
            content=body.model_dump(),
            status_code=200 if healthy else 503,
        )

    return app


app = create_app()

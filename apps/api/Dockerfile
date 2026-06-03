# syntax=docker/dockerfile:1
# WP Plugin Support Desk RAG — application image.
# Author: Al Amin Ahamed.
#
# Single image used by the api, worker, and beat services; the command differs
# per service in docker-compose. Dependencies are installed with uv against the
# committed lockfile for reproducible builds (NFR-PT-1).
#
# Build context: repo root (required for packages/wp_support_rag_sdk path dep).
# The monorepo layout is mirrored inside the container so uv can resolve the
# relative path "../../packages/wp_support_rag_sdk" from apps/api/pyproject.toml.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

# uv: pinned copy from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

# Mirror monorepo layout so relative path deps resolve correctly.
# pyproject.toml references "../../packages/wp_support_rag_sdk" which from
# /workspace/apps/api resolves to /workspace/packages/wp_support_rag_sdk.
WORKDIR /workspace/apps/api

# Copy the SDK package first (needed by uv lock resolution).
COPY packages/wp_support_rag_sdk /workspace/packages/wp_support_rag_sdk

# Install dependencies against the lockfile for layer caching.
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source.
COPY apps/api/app ./app
COPY apps/api/eval ./eval
COPY apps/api/alembic.ini ./alembic.ini

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Default command runs the API; worker/beat override this in compose.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

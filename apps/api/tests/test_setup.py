"""Tests for GET /api/v1/admin/setup/status and POST /api/v1/admin/setup/complete.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.deps import get_settings_dep
from app.auth.jwt import UserClaims, create_access_token
from app.config import Settings
from app.db.engine import dispose_engine, get_sessionmaker
from app.db.models import SystemSetting
from app.db.redis import close_redis, get_redis
from app.main import create_app

from tests.conftest import database_available

_JWT_SECRET = "test-jwt-secret"  # noqa: S105
_STATUS_URL = "/api/v1/admin/setup/status"
_COMPLETE_URL = "/api/v1/admin/setup/complete"


def _test_settings(**kwargs) -> Settings:  # type: ignore[return]
    return Settings(jwt_secret=_JWT_SECRET, bootstrap_email=None, bootstrap_password=None, **kwargs)


def _cookie(permissions: list[str]) -> dict[str, str]:
    claims = UserClaims(
        sub=str(uuid.uuid4()),
        email="admin@test.com",
        roles=["super_admin"],
        permissions=permissions,
    )
    token = create_access_token(claims, secret=_JWT_SECRET, ttl_seconds=300)
    return {"access_token": token}


async def _clear_system_settings() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(delete(SystemSetting))
        await session.commit()
    await dispose_engine()
    await close_redis()
    for cached in (get_sessionmaker, get_redis):
        cached.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_settings_dep] = lambda: _test_settings()
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def _ready() -> None:
    if not await database_available():
        pytest.skip("no migrated PostgreSQL+pgvector database reachable")
    await _clear_system_settings()


@pytest.mark.asyncio
async def test_get_setup_status_returns_false_when_no_row(_ready: None, client: TestClient) -> None:
    resp = client.get(_STATUS_URL, cookies=_cookie([]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": False}


@pytest.mark.asyncio
async def test_post_setup_complete_marks_complete(_ready: None, client: TestClient) -> None:
    resp = client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": True}

    resp2 = client.get(_STATUS_URL, cookies=_cookie([]))
    assert resp2.status_code == 200
    assert resp2.json() == {"complete": True}


@pytest.mark.asyncio
async def test_post_setup_complete_is_idempotent(_ready: None, client: TestClient) -> None:
    client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    resp = client.post(_COMPLETE_URL, cookies=_cookie(["settings:write"]))
    assert resp.status_code == 200
    assert resp.json() == {"complete": True}


@pytest.mark.asyncio
async def test_setup_complete_requires_settings_write(_ready: None, client: TestClient) -> None:
    resp = client.post(_COMPLETE_URL, cookies=_cookie([]))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_setup_status_requires_auth(client: TestClient) -> None:
    resp = client.get(_STATUS_URL)  # no cookie
    assert resp.status_code == 401

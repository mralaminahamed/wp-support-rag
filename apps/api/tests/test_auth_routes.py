"""Tests for /api/v1/auth/* endpoints.

Uses TestClient with dependency overrides — no live database required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import main
from app.auth.jwt import UserClaims
from app.config import Settings
from fastapi.testclient import TestClient


def _settings(**kwargs):
    return Settings(
        jwt_secret="test-secret",
        bootstrap_email=None,
        bootstrap_password=None,
        **kwargs,
    )


def _make_user(email="a@example.com", active=True):
    """Return a mock ORM User with a super_admin role."""
    role = MagicMock()
    role.name = "super_admin"
    role.permissions = [MagicMock(permission="plugins:read")]

    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = email
    user.is_active = active
    user.password_hash = "$2b$12$KIXf5k1qo7GUfmC8bBuV2OobzH2PBvJt3rT0TUJJpR1F7z4GaKEtu"
    user.roles = [role]
    user.permissions = []
    user.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return user


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    return TestClient(main.create_app(), raise_server_exceptions=False)


def test_login_returns_200_and_sets_cookie(client: TestClient) -> None:
    """POST /login with valid creds sets access_token cookie."""
    user = _make_user()
    with (
        patch("app.api.routes_auth.get_user_by_email", new=AsyncMock(return_value=user)),
        patch("app.api.routes_auth.verify_password", return_value=True),
        patch("app.api.routes_auth._create_refresh_token", new=AsyncMock(return_value="raw-token")),
    ):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "a@example.com", "password": "secret"},
        )
    assert resp.status_code == 200
    assert "access_token" in resp.cookies


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    """POST /login with wrong password → 401."""
    user = _make_user()
    with (
        patch("app.api.routes_auth.get_user_by_email", new=AsyncMock(return_value=user)),
        patch("app.api.routes_auth.verify_password", return_value=False),
    ):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "a@example.com", "password": "wrong"},
        )
    assert resp.status_code == 401


def test_login_unknown_user_returns_401(client: TestClient) -> None:
    """POST /login with unknown email → 401."""
    with patch("app.api.routes_auth.get_user_by_email", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "x"},
        )
    assert resp.status_code == 401


def test_me_with_valid_cookie_returns_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /me with a valid access_token cookie → 200."""
    from app.api.deps import get_settings_dep
    from app.auth.jwt import create_access_token
    from app.db.engine import get_session

    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    claims = UserClaims(sub=str(uuid.uuid4()), email="a@b.com", roles=["admin"],
                        permissions=["plugins:read"])
    token = create_access_token(claims, secret="test-secret", ttl_seconds=300)

    user = _make_user(email="a@b.com")

    async def mock_session_dep():
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=user)
        mock_session.refresh = AsyncMock()
        yield mock_session

    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: _settings()
    app_obj.dependency_overrides[get_session] = mock_session_dep

    client = TestClient(app_obj, cookies={"access_token": token}, raise_server_exceptions=False)
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["email"] == "a@b.com"


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    """GET /me without cookie → 401."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_register_disabled_by_default(client: TestClient) -> None:
    """POST /register returns 403 when allow_registration is false."""
    resp = client.post("/api/v1/auth/register",
                       json={"email": "new@example.com", "password": "password123"})
    assert resp.status_code == 403


def test_register_enabled_creates_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /register creates a viewer user when allow_registration=true."""
    from app.api.deps import get_settings_dep

    monkeypatch.setattr(main, "get_settings", lambda: _settings(allow_registration=True))
    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: _settings(allow_registration=True)
    client = TestClient(app_obj, raise_server_exceptions=False)
    user = _make_user()
    with (
        patch("app.api.routes_auth.get_user_by_email", new=AsyncMock(return_value=None)),
        patch("app.api.routes_auth._create_user_with_role", new=AsyncMock(return_value=user)),
        patch("app.api.routes_auth._create_refresh_token", new=AsyncMock(return_value="tok")),
    ):
        resp = client.post("/api/v1/auth/register",
                           json={"email": "new@example.com", "password": "password123"})
    assert resp.status_code == 201

"""Tests for /api/v1/admin/users and /api/v1/admin/roles endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import main
from app.api.deps import get_settings_dep
from app.auth.jwt import UserClaims, create_access_token
from app.config import Settings
from fastapi.testclient import TestClient


def _settings():
    return Settings(jwt_secret="test-secret", bootstrap_email=None, bootstrap_password=None)


def _auth_cookie(permissions: list[str]) -> dict[str, str]:
    claims = UserClaims(
        sub=str(uuid.uuid4()), email="admin@x.com",
        roles=["super_admin"], permissions=permissions,
    )
    token = create_access_token(claims, secret="test-secret", ttl_seconds=300)
    return {"access_token": token}


@pytest.fixture
def client_admin(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: _settings()
    return TestClient(
        app_obj,
        cookies=_auth_cookie(["users:read", "users:write", "users:invite"]),
        raise_server_exceptions=False,
    )


@pytest.fixture
def client_viewer(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(main, "get_settings", lambda: _settings())
    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: _settings()
    return TestClient(
        app_obj,
        cookies=_auth_cookie(["plugins:read"]),  # no users:read
        raise_server_exceptions=False,
    )


def test_list_users_requires_users_read(client_viewer: TestClient) -> None:
    """GET /admin/users requires users:read — viewer gets 403."""
    resp = client_viewer.get("/api/v1/admin/users")
    assert resp.status_code == 403


def test_list_users_returns_200(client_admin: TestClient) -> None:
    """GET /admin/users returns list for users:read holder."""
    with patch("app.api.routes_users._list_users", new=AsyncMock(return_value=[])):
        resp = client_admin.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_user_returns_201(client_admin: TestClient) -> None:
    """POST /admin/users creates a user for users:write holder."""
    uid = uuid.uuid4()
    mock_user = MagicMock()
    mock_user.id = uid
    mock_user.email = "new@x.com"
    mock_user.is_active = True
    mock_role = MagicMock()
    mock_role.name = "viewer"
    mock_role.permissions = []
    mock_user.roles = [mock_role]
    mock_user.permissions = []

    with patch("app.api.routes_users._create_user", new=AsyncMock(return_value=mock_user)):
        resp = client_admin.post(
            "/api/v1/admin/users",
            json={"email": "new@x.com", "password": "password123", "role_ids": []},
        )
    assert resp.status_code == 201


def test_delete_user_returns_204(client_admin: TestClient) -> None:
    """DELETE /admin/users/{id} returns 204 for users:write holder."""
    uid = uuid.uuid4()
    with patch("app.api.routes_users._delete_user", new=AsyncMock(return_value=None)):
        resp = client_admin.delete(f"/api/v1/admin/users/{uid}")
    assert resp.status_code == 204


def test_list_roles_returns_200(client_admin: TestClient) -> None:
    """GET /admin/roles returns list for users:read holder."""
    with patch("app.api.routes_users._list_roles", new=AsyncMock(return_value=[])):
        resp = client_admin.get("/api/v1/admin/roles")
    assert resp.status_code == 200


def test_create_role_requires_users_write(client_viewer: TestClient) -> None:
    """POST /admin/roles requires users:write — viewer gets 403."""
    resp = client_viewer.post("/api/v1/admin/roles",
                              json={"name": "tester", "permissions": []})
    assert resp.status_code == 403

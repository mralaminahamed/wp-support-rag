"""Tests for /api/v1/admin/adapter-plugins endpoints.

All DB and disk I/O are patched so these tests run without a live database,
Redis, or filesystem. Auth is exercised via JWT cookies injected by the test
client.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app import main
from app.api.deps import get_settings_dep
from app.auth.jwt import UserClaims, create_access_token
from app.config import Settings
from app.ingestion.adapter_registry import AdapterRegistry, AdapterTypeInfo, init_registry
from fastapi.testclient import TestClient

_JWT_SECRET = "test-adapter-secret"  # noqa: S105


def _settings(**kwargs) -> Settings:
    return Settings(
        jwt_secret=_JWT_SECRET,
        bootstrap_email=None,
        bootstrap_password=None,
        **kwargs,
    )


def _auth_cookie(permissions: list[str]) -> dict[str, str]:
    claims = UserClaims(
        sub=str(uuid.uuid4()),
        email="admin@test.com",
        roles=["super_admin"],
        permissions=permissions,
    )
    token = create_access_token(claims, secret=_JWT_SECRET, ttl_seconds=300)
    return {"access_token": token}


def _make_adapter_row(
    slug: str = "builtin.github",
    display_name: str = "GitHub",
    source: str = "builtin",
    handles: list[str] | None = None,
    status: str = "loaded",
    error: str | None = None,
    filename: str | None = None,
) -> MagicMock:
    """Build a MagicMock that looks like an AdapterPlugin ORM row."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.slug = slug
    row.display_name = display_name
    row.version = None
    row.source = source
    row.entry_point = None
    row.filename = filename
    row.handles = handles or ["github_readme", "github_changelog"]
    row.config_schema = {}
    row.status = status
    row.error = error
    row.installed_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return row


def _make_type_info(source_type: str = "github_readme") -> AdapterTypeInfo:
    return AdapterTypeInfo(
        source_type=source_type,
        display_name="GitHub",
        adapter_slug="builtin.github",
        config_schema={},
        is_builtin=True,
        multi_instance=True,
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    """TestClient wired with settings:read + settings:write permissions.

    Patches settings so no real DB/Redis is needed at app-factory time.
    Uses tmp_path as the custom_adapters_dir.
    """
    s = _settings(custom_adapters_dir=str(tmp_path))
    monkeypatch.setattr(main, "get_settings", lambda: s)
    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: s
    return TestClient(
        app_obj,
        cookies=_auth_cookie(["settings:read", "settings:write"]),
        raise_server_exceptions=False,
    )


@pytest.fixture
def client_readonly(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    """TestClient with only settings:read permission."""
    s = _settings(custom_adapters_dir=str(tmp_path))
    monkeypatch.setattr(main, "get_settings", lambda: s)
    app_obj = main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: s
    return TestClient(
        app_obj,
        cookies=_auth_cookie(["settings:read"]),
        raise_server_exceptions=False,
    )


# ---------------------------------------------------------------------------
# GET /adapter-plugins
# ---------------------------------------------------------------------------


def test_list_adapter_plugins_returns_list(client: TestClient) -> None:
    """GET /adapter-plugins returns a list of adapter plugins."""
    rows = [
        _make_adapter_row("builtin.github", "GitHub", "builtin"),
        _make_adapter_row("builtin.wporg", "WordPress.org", "builtin", handles=["wporg_faq"]),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    with patch("app.api.routes_adapters.get_session") as mock_gs:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_gs.return_value.__aiter__ = None

        from app.db.engine import get_session as real_get_session

        async def _override_session():
            yield mock_session

        client.app.dependency_overrides[real_get_session] = _override_session

        resp = client.get("/api/v1/admin/adapter-plugins")

    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["slug"] == "builtin.github"
    assert data[1]["slug"] == "builtin.wporg"


def test_list_adapter_plugins_requires_auth(client_readonly: TestClient) -> None:
    """GET /adapter-plugins allows settings:read."""
    rows = []
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    from app.db.engine import get_session as real_get_session

    async def _override_session():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    client_readonly.app.dependency_overrides[real_get_session] = _override_session
    resp = client_readonly.get("/api/v1/admin/adapter-plugins")
    client_readonly.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /adapter-plugins/types
# ---------------------------------------------------------------------------


def test_list_adapter_types_returns_types(client: TestClient) -> None:
    """GET /adapter-plugins/types returns AdapterTypeInfo list from registry."""
    type_infos = [
        _make_type_info("github_readme"),
        _make_type_info("wporg_faq"),
    ]
    mock_registry = MagicMock()
    mock_registry.types_with_schema.return_value = type_infos

    with patch("app.api.routes_adapters.get_registry", return_value=mock_registry):
        resp = client.get("/api/v1/admin/adapter-plugins/types")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["source_type"] == "github_readme"
    assert data[0]["adapter_slug"] == "builtin.github"
    assert data[0]["is_builtin"] is True
    assert data[1]["source_type"] == "wporg_faq"


def test_list_adapter_types_requires_settings_read() -> None:
    """GET /adapter-plugins/types requires settings:read — unauthenticated gets 401."""
    import uuid
    from app.auth.jwt import UserClaims, create_access_token

    claims = UserClaims(
        sub=str(uuid.uuid4()),
        email="viewer@test.com",
        roles=["viewer"],
        permissions=["plugins:read"],  # no settings:read
    )
    token = create_access_token(claims, secret=_JWT_SECRET, ttl_seconds=300)

    # Use a fresh client with only plugins:read
    import app.main as _main

    s = _settings()
    app_obj = _main.create_app()
    app_obj.dependency_overrides[get_settings_dep] = lambda: s
    c = TestClient(
        app_obj,
        cookies={"access_token": token},
        raise_server_exceptions=False,
    )
    resp = c.get("/api/v1/admin/adapter-plugins/types")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /adapter-plugins/upload
# ---------------------------------------------------------------------------

_VALID_ADAPTER_PY = """\
class MyCustomAdapter:
    handles = ("custom_source_type",)
    display_name = "My Custom Adapter"
    config_schema = {}

    async def fetch(self, ctx):
        return
        yield
"""

_INVALID_PYTHON = "def oops(: invalid syntax here!!!"

_NO_ADAPTER_CLASS = """\
# valid Python but no adapter class
def helper():
    pass
"""


def test_upload_valid_adapter_returns_loaded(client: TestClient, tmp_path) -> None:
    """POST /upload with a valid .py adapter returns 200 with status='loaded'."""
    content = _VALID_ADAPTER_PY.encode()

    from app.db.engine import get_session as real_get_session

    mock_row = _make_adapter_row(
        slug="file.my_adapter.MyCustomAdapter",
        display_name="My Custom Adapter",
        source="file",
        handles=["custom_source_type"],
        filename="my_adapter.py",
    )

    # Make execute return a result for the conflict check (empty) and the fetch-back
    call_count = 0

    async def _fake_execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        if call_count == 1:
            # conflict check — no conflicts
            mock_result.scalars.return_value.all.return_value = []
        else:
            # fetch-back after upsert
            mock_result.scalar_one.return_value = mock_row
        return mock_result

    async def _fake_commit():
        pass

    async def _override_session():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_fake_execute)
        mock_session.commit = AsyncMock(side_effect=_fake_commit)
        yield mock_session

    client.app.dependency_overrides[real_get_session] = _override_session

    # Patch get_settings inside routes_adapters to use tmp_path
    with patch("app.api.routes_adapters.get_settings", return_value=_settings(custom_adapters_dir=str(tmp_path))):
        resp = client.post(
            "/api/v1/admin/adapter-plugins/upload",
            files={"file": ("my_adapter.py", content, "text/x-python")},
        )

    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "file.my_adapter.MyCustomAdapter"
    assert data["status"] == "loaded"
    assert data["source"] == "file"


def test_upload_non_py_returns_422(client: TestClient) -> None:
    """POST /upload with a non-.py file returns 422."""
    resp = client.post(
        "/api/v1/admin/adapter-plugins/upload",
        files={"file": ("my_adapter.txt", b"content", "text/plain")},
    )
    assert resp.status_code == 422
    assert "only .py files" in resp.json()["detail"]


def test_upload_invalid_python_returns_error_status(client: TestClient, tmp_path) -> None:
    """POST /upload with invalid Python returns 200 with status='error'."""
    content = _INVALID_PYTHON.encode()

    from app.db.engine import get_session as real_get_session

    mock_error_row = _make_adapter_row(
        slug="file.bad_adapter.unknown",
        display_name="bad_adapter",
        source="file",
        handles=[],
        status="error",
        error="invalid syntax",
        filename="bad_adapter.py",
    )

    call_count = 0

    async def _fake_execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_error_row
        mock_result.scalars.return_value.all.return_value = []
        return mock_result

    async def _override_session():
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=_fake_execute)
        mock_session.commit = AsyncMock()
        yield mock_session

    client.app.dependency_overrides[real_get_session] = _override_session

    with patch("app.api.routes_adapters.get_settings", return_value=_settings(custom_adapters_dir=str(tmp_path))):
        resp = client.post(
            "/api/v1/admin/adapter-plugins/upload",
            files={"file": ("bad_adapter.py", content, "text/x-python")},
        )

    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


# ---------------------------------------------------------------------------
# DELETE /adapter-plugins/{slug}
# ---------------------------------------------------------------------------


def test_delete_builtin_adapter_returns_403(client: TestClient) -> None:
    """DELETE /adapter-plugins/builtin.github returns 403 — builtins cannot be deleted."""
    builtin_row = _make_adapter_row("builtin.github", "GitHub", "builtin")

    from app.db.engine import get_session as real_get_session

    async def _override_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = builtin_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    client.app.dependency_overrides[real_get_session] = _override_session
    resp = client.delete("/api/v1/admin/adapter-plugins/builtin.github")
    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 403
    assert "only file-based" in resp.json()["detail"]


def test_delete_file_adapter_returns_204(client: TestClient, tmp_path) -> None:
    """DELETE /adapter-plugins/file.my_adapter.MyCustomAdapter returns 204."""
    # Write a dummy file to tmp_path so unlink is exercised
    adapter_file = tmp_path / "my_adapter.py"
    adapter_file.write_text(_VALID_ADAPTER_PY)

    file_row = _make_adapter_row(
        slug="file.my_adapter.MyCustomAdapter",
        display_name="My Custom Adapter",
        source="file",
        handles=["custom_source_type"],
        filename="my_adapter.py",
    )

    from app.db.engine import get_session as real_get_session

    async def _override_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = file_row
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        yield mock_session

    client.app.dependency_overrides[real_get_session] = _override_session

    with patch("app.api.routes_adapters.get_settings", return_value=_settings(custom_adapters_dir=str(tmp_path))):
        resp = client.delete(
            "/api/v1/admin/adapter-plugins/file.my_adapter.MyCustomAdapter"
        )

    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 204
    # File should be deleted
    assert not adapter_file.exists()


def test_delete_nonexistent_adapter_returns_404(client: TestClient) -> None:
    """DELETE /adapter-plugins/unknown.slug returns 404."""
    from app.db.engine import get_session as real_get_session

    async def _override_session():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        yield mock_session

    client.app.dependency_overrides[real_get_session] = _override_session
    resp = client.delete("/api/v1/admin/adapter-plugins/unknown.slug")
    client.app.dependency_overrides.pop(real_get_session, None)

    assert resp.status_code == 404

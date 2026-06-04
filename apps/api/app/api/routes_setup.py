"""Setup wizard endpoints — first-run status, reset, network config, admin creation.

All endpoints except ``complete`` are unauthenticated; they guard themselves by
refusing to operate when ``setup_complete`` is already ``"true"``.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings_dep, require_permission
from app.api.schemas import (
    CreateAdminRequest,
    CreateAdminResponse,
    NetworkConfigRequest,
    NetworkConfigResponse,
    SetupStatusResponse,
)
from app.auth.jwt import UserClaims, create_access_token
from app.auth.password import hash_password
from app.auth.permissions import resolve_permissions
from app.config import Settings
from app.db.engine import get_session
from app.db.models import RefreshToken, Role, SystemSetting, User, UserRole

router = APIRouter(prefix="/api/v1/admin", tags=["setup"])

_KEY_SETUP = "setup_complete"
_KEY_ADMIN_URL = "admin_url"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _assert_setup_incomplete(session: AsyncSession) -> None:
    """Raise 403 when setup has already been completed."""
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == _KEY_SETUP))
    if row is not None and row.value == "true":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="setup already complete")


def _cookie_kw(settings: Settings, *, path: str = "/") -> dict:
    return {
        "httponly": True,
        "samesite": "strict",
        "secure": settings.environment == "production",
        "path": path,
    }


async def _issue_session(
    response: Response,
    session: AsyncSession,
    user: User,
    settings: Settings,
) -> None:
    """Set access + refresh cookies for a freshly created user."""
    perms = sorted(resolve_permissions(
        [[rp.permission for rp in role.permissions] for role in user.roles],
        [(up.permission, up.granted) for up in user.permissions],
    ))
    claims = UserClaims(
        sub=str(user.id),
        email=user.email,
        roles=[r.name for r in user.roles],
        permissions=perms,
    )
    token = create_access_token(
        claims,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_seconds=settings.access_token_ttl_seconds,
    )
    response.set_cookie(
        "access_token",
        token,
        max_age=settings.access_token_ttl_seconds,
        **_cookie_kw(settings),
    )

    raw_refresh = str(uuid.uuid4())
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_refresh.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    session.add(rt)
    await session.commit()
    response.set_cookie(
        "refresh_token",
        raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        **_cookie_kw(settings, path="/api/v1/auth/refresh"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/setup/status", response_model=SetupStatusResponse)
async def get_setup_status(
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Return whether the first-run setup wizard has been completed.

    Public — no authentication required. Returns ``complete: false`` when the
    ``setup_complete`` key is absent or not ``"true"``.
    """
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == _KEY_SETUP))
    return SetupStatusResponse(complete=row is not None and row.value == "true")


@router.post("/setup/reset", status_code=status.HTTP_200_OK)
async def reset_system(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Wipe all user-generated data and reset the system to factory state.

    Only works when setup is not yet complete. Truncates users, plugins,
    invite_tokens, and system_settings (cascading to all dependent tables).
    The built-in roles and role_permissions seed data are preserved.
    """
    await _assert_setup_incomplete(session)
    await session.execute(
        text(
            "TRUNCATE TABLE users, plugins, invite_tokens, system_settings"
            " RESTART IDENTITY CASCADE"
        )
    )
    await session.commit()
    return {"wiped": True}


@router.get("/setup/network", response_model=NetworkConfigResponse)
async def get_network_config(
    session: AsyncSession = Depends(get_session),
) -> NetworkConfigResponse:
    """Return the stored admin URL from system settings. Public endpoint."""
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == _KEY_ADMIN_URL))
    return NetworkConfigResponse(admin_url=row.value if row else None)


@router.put("/setup/network", status_code=status.HTTP_204_NO_CONTENT)
async def save_network_config(
    body: NetworkConfigRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Persist the admin URL to system settings.

    Only works when setup is not yet complete. The URL is used by the API for
    building server-generated links (invites, password-reset emails, etc.).
    """
    await _assert_setup_incomplete(session)
    stmt = (
        pg_insert(SystemSetting)
        .values(key=_KEY_ADMIN_URL, value=body.admin_url)
        .on_conflict_do_update(index_elements=["key"], set_={"value": body.admin_url})
    )
    await session.execute(stmt)
    await session.commit()


@router.post("/setup/create-admin", response_model=CreateAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: CreateAdminRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> CreateAdminResponse:
    """Create the first super-admin account and issue session cookies.

    Only works when setup is not yet complete. Wipes any existing users before
    creating the new account so navigating directly to this step (skipping the
    explicit reset in the network step) still produces a clean state.
    Issues access + refresh cookies so subsequent wizard steps work without
    the user having to log in separately.
    """
    await _assert_setup_incomplete(session)

    # Wipe existing users (cascade handles user_roles, refresh_tokens, etc.).
    # This makes the step idempotent: works whether or not /setup/reset was called.
    await session.execute(text("TRUNCATE TABLE users RESTART IDENTITY CASCADE"))
    await session.commit()

    role = await session.scalar(select(Role).where(Role.name == "super_admin"))
    if role is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="super_admin role not seeded")

    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.commit()
    await session.refresh(user)

    await _issue_session(response, session, user, settings)
    return CreateAdminResponse(id=str(user.id), email=user.email)


@router.post("/setup/complete", response_model=SetupStatusResponse)
async def complete_setup(
    _: UserClaims = Depends(require_permission("settings:write")),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Mark the first-run setup wizard as complete and sync settings to .env."""
    stmt = (
        pg_insert(SystemSetting)
        .values(key=_KEY_SETUP, value="true")
        .on_conflict_do_update(index_elements=["key"], set_={"value": "true"})
    )
    await session.execute(stmt)
    await session.commit()
    # Best-effort: sync DB settings to .env so env defaults survive a full
    # Redis+DB wipe. Silently ignored if .env is not mounted.
    try:
        from app.api.routes_admin import _ENV_FILE, _EMBED_MODEL_KEY, _LLM_MODEL_KEY, _set_env_var  # noqa: PLC0415
        rows = await session.execute(
            select(SystemSetting).where(
                SystemSetting.key.in_(["llm:provider", "llm:model", "embed:provider", "embed:model"])
            )
        )
        settings_map = {row.key: row.value for row in rows.scalars()}
        if _ENV_FILE.exists() and settings_map:
            content = _ENV_FILE.read_text(encoding="utf-8")
            if provider := settings_map.get("llm:provider"):
                content = _set_env_var(content, "WPRAG_DEFAULT_PROVIDER", provider)
                if model := settings_map.get("llm:model"):
                    if model_key := _LLM_MODEL_KEY.get(provider):
                        content = _set_env_var(content, model_key, model)
            if embed_provider := settings_map.get("embed:provider"):
                content = _set_env_var(content, "WPRAG_EMBEDDING_PROVIDER", embed_provider)
                if embed_model := settings_map.get("embed:model"):
                    if embed_key := _EMBED_MODEL_KEY.get(embed_provider):
                        content = _set_env_var(content, embed_key, embed_model)
            _ENV_FILE.write_text(content, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return SetupStatusResponse(complete=True)

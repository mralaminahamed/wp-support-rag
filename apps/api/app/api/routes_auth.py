"""Auth endpoints: login, logout, refresh, me, register, accept-invite,
forgot-password, reset-password.

Sets and clears HTTP-only SameSite=Strict cookies. Access tokens are short-lived
JWTs (15 min); refresh tokens are opaque UUIDs stored hashed in the DB (7 days).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings_dep
from app.api.schemas import (
    AcceptInviteRequest,
    AuthUserResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.auth.jwt import UserClaims, create_access_token, verify_jwt
from app.auth.password import hash_password, verify_password
from app.auth.permissions import resolve_permissions
from app.config import Settings
from app.db.engine import get_session
from app.db.models import InviteToken, PasswordResetToken, RefreshToken, Role, User, UserRole
from app.email import send_password_reset, send_welcome

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _cookie_kwargs(settings: Settings, *, path: str = "/") -> dict:
    return {
        "httponly": True,
        "samesite": "strict",
        "secure": settings.environment == "production",
        "path": path,
    }


def _effective_permissions(user: User) -> list[str]:
    role_perm_lists = [[rp.permission for rp in role.permissions] for role in user.roles]
    overrides = [(up.permission, up.granted) for up in user.permissions]
    return sorted(resolve_permissions(role_perm_lists, overrides))


def _user_response(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        roles=[r.name for r in user.roles],
        permissions=_effective_permissions(user),
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


def _set_access_cookie(response: Response, user: User, settings: Settings) -> None:
    claims = UserClaims(
        sub=str(user.id),
        email=user.email,
        roles=[r.name for r in user.roles],
        permissions=_effective_permissions(user),
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
        **_cookie_kwargs(settings),
    )


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


async def _create_refresh_token(session: AsyncSession, user: User, ttl: int) -> str:
    raw = str(uuid.uuid4())
    rt = RefreshToken(
        user_id=user.id,
        token_hash=_token_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
    )
    session.add(rt)
    await session.commit()
    return raw


async def _create_user_with_role(
    session: AsyncSession, email: str, password: str, role_name: str
) -> User:
    role = (await session.execute(select(Role).where(Role.name == role_name))).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=500, detail=f"role '{role_name}' not seeded")
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AuthUserResponse:
    """Authenticate with email + password; set HTTP-only session cookies."""
    user = await get_user_by_email(session, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account inactive")

    _set_access_cookie(response, user, settings)

    raw_refresh = await _create_refresh_token(session, user, settings.refresh_token_ttl_seconds)
    response.set_cookie(
        "refresh_token",
        raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        **_cookie_kwargs(settings, path="/api/v1/auth/refresh"),
    )
    return _user_response(user)


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> dict:
    """Exchange a valid refresh_token cookie for a new access_token."""
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no refresh token")
    rt = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == _token_hash(raw))
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if rt is None or rt.revoked_at is not None or rt.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token invalid")

    user = await session.get(User, rt.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account inactive")

    # Refresh token rotation: revoke the consumed token, then issue a new one.
    rt.revoked_at = now
    await session.commit()

    await session.refresh(user)
    _set_access_cookie(response, user, settings)

    new_raw_refresh = await _create_refresh_token(session, user, settings.refresh_token_ttl_seconds)
    response.set_cookie(
        "refresh_token",
        new_raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        **_cookie_kwargs(settings, path="/api/v1/auth/refresh"),
    )
    return {"ok": True}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Revoke the refresh token and clear both session cookies."""
    raw = request.cookies.get("refresh_token")
    if raw:
        rt = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == _token_hash(raw))
            )
        ).scalar_one_or_none()
        if rt and rt.revoked_at is None:
            rt.revoked_at = datetime.now(timezone.utc)
            await session.commit()
    response.delete_cookie("access_token", **_cookie_kwargs(settings))
    response.delete_cookie("refresh_token", **_cookie_kwargs(settings, path="/api/v1/auth/refresh"))


@router.get("/me", status_code=status.HTTP_200_OK)
async def me(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AuthUserResponse:
    """Return the current user's identity from the access_token cookie."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    claims = verify_jwt(token, secret=settings.jwt_secret.get_secret_value())
    user = await session.get(User, uuid.UUID(claims.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account inactive")
    await session.refresh(user)
    return _user_response(user)


@router.patch("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AuthUserResponse:
    """Verify current password and set a new one for the authenticated user."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    claims = verify_jwt(token, secret=settings.jwt_secret.get_secret_value())
    user = await session.get(User, uuid.UUID(claims.sub))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="account inactive")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    await session.refresh(user)
    _set_access_cookie(response, user, settings)
    return _user_response(user)


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AuthUserResponse:
    """Open registration (gated by WPRAG_ALLOW_REGISTRATION)."""
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="registration disabled")
    if await get_user_by_email(session, payload.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    user = await _create_user_with_role(session, payload.email, payload.password, "viewer")
    _set_access_cookie(response, user, settings)
    raw_refresh = await _create_refresh_token(session, user, settings.refresh_token_ttl_seconds)
    response.set_cookie(
        "refresh_token",
        raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        **_cookie_kwargs(settings, path="/api/v1/auth/refresh"),
    )
    return _user_response(user)


@router.post("/accept-invite", status_code=status.HTTP_201_CREATED)
async def accept_invite(
    payload: AcceptInviteRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> AuthUserResponse:
    """Accept an invite token and set a password to create an account."""
    invite = (
        await session.execute(
            select(InviteToken).where(InviteToken.token_hash == _token_hash(payload.token))
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if invite is None or invite.used_at is not None or invite.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired invite")
    if await get_user_by_email(session, invite.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    role_name = "viewer"
    if invite.role_id:
        role = await session.get(Role, invite.role_id)
        if role:
            role_name = role.name

    user = await _create_user_with_role(session, invite.email, payload.password, role_name)
    invite.used_at = now
    await session.commit()

    _set_access_cookie(response, user, settings)
    raw_refresh = await _create_refresh_token(session, user, settings.refresh_token_ttl_seconds)
    response.set_cookie(
        "refresh_token",
        raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        **_cookie_kwargs(settings, path="/api/v1/auth/refresh"),
    )

    # Welcome email — fire-and-forget; non-fatal if SMTP unconfigured or fails.
    try:
        await send_welcome(settings, to=invite.email)
    except Exception:
        logger.exception("failed to send welcome email to %s", invite.email)

    return _user_response(user)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    """Send a password-reset link to the given email.

    Always returns 204 regardless of whether the email is registered to prevent
    user enumeration.
    """
    user = await get_user_by_email(session, payload.email)
    if user is None or not user.is_active:
        return  # silent — don't reveal whether the address is registered

    raw = str(uuid.uuid4())
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=_token_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.password_reset_ttl_seconds),
    )
    session.add(token)
    await session.commit()

    if settings.admin_url:
        reset_url = f"{settings.admin_url.rstrip('/')}/reset-password?token={raw}"
        try:
            await send_password_reset(settings, to=user.email, reset_url=reset_url)
        except Exception:
            logger.exception("failed to send password-reset email to %s", user.email)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Consume a password-reset token and update the user's password."""
    token = (
        await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == _token_hash(payload.token)
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired token")

    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid or expired token")

    user.password_hash = hash_password(payload.password)
    token.used_at = now
    await session.commit()

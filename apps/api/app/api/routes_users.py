"""User and role management endpoints for the admin console.

All endpoints require cookie-based authentication; access is gated by
require_permission with the appropriate permission string.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings_dep, require_permission
from app.api.schemas import (
    AuthUserResponse,
    CreateRoleRequest,
    CreateUserRequest,
    InviteRequest,
    InviteResponse,
    InviteSummary,
    PatchRoleRequest,
    PatchUserRequest,
    RoleSummary,
    UserListItem,
)
from app.auth.password import hash_password
from app.auth.permissions import resolve_permissions
from app.config import Settings
from app.db.engine import get_session
from app.db.models import ConversationThread, InviteToken, Role, RolePermission, SystemSetting, User, UserRole
from app.email import send_invite

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["users"])


# ---------------------------------------------------------------------------
# Internal helpers (module-level so tests can patch them)
# ---------------------------------------------------------------------------

async def _resolve_admin_url(session: AsyncSession, settings: Settings) -> str | None:
    """Return admin_url: DB system_settings first, env var fallback."""
    row = await session.scalar(select(SystemSetting).where(SystemSetting.key == "admin_url"))
    return (row.value if row else None) or settings.admin_url or None


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


async def _list_users(session: AsyncSession) -> list[User]:
    return list((await session.execute(select(User).order_by(User.created_at))).scalars().all())


async def _create_user(
    session: AsyncSession, email: str, password: str, role_ids: list[uuid.UUID]
) -> User:
    if (await session.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    for rid in role_ids:
        session.add(UserRole(user_id=user.id, role_id=rid))
    await session.commit()
    await session.refresh(user)
    return user


async def _delete_user(session: AsyncSession, user_id: uuid.UUID, caller_id: str) -> None:
    if str(user_id) == caller_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot delete own account")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    await session.delete(user)
    await session.commit()


async def _list_roles(session: AsyncSession) -> list[Role]:
    return list((await session.execute(select(Role).order_by(Role.name))).scalars().all())


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[UserListItem])
async def list_users(
    _: None = Depends(require_permission("users:read")),
    session: AsyncSession = Depends(get_session),
) -> list[UserListItem]:
    """List all admin-console user accounts."""
    users = await _list_users(session)
    if users:
        counts_rows = (await session.execute(
            select(ConversationThread.user_id, func.count(ConversationThread.id).label("cnt"))
            .where(ConversationThread.user_id.in_([u.id for u in users]))
            .group_by(ConversationThread.user_id)
        )).all()
        thread_counts = {str(row.user_id): row.cnt for row in counts_rows}
    else:
        thread_counts = {}
    return [
        UserListItem(
            id=u.id,
            email=u.email,
            roles=[r.name for r in u.roles],
            permissions=_effective_permissions(u),
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
            thread_count=thread_counts.get(str(u.id), 0),
        )
        for u in users
    ]


@router.post("/users", status_code=status.HTTP_201_CREATED, response_model=AuthUserResponse)
async def create_user(
    payload: CreateUserRequest,
    _: None = Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> AuthUserResponse:
    """Create a new user account with assigned roles."""
    user = await _create_user(session, payload.email, payload.password, payload.role_ids)
    return _user_response(user)


@router.get("/users/invites", response_model=list[InviteSummary])
async def list_invites(
    _: object = Depends(require_permission("users:invite")),
    session: AsyncSession = Depends(get_session),
) -> list[InviteSummary]:
    """List all invite tokens with derived status."""
    rows = await session.execute(
        select(InviteToken, Role.name.label("role_name"))
        .outerjoin(Role, Role.id == InviteToken.role_id)
        .order_by(InviteToken.expires_at.desc())
    )
    now = datetime.now(timezone.utc)
    result = []
    for invite, role_name in rows:
        if invite.used_at is not None:
            st = "accepted"
        elif invite.expires_at < now:
            st = "expired"
        else:
            st = "pending"
        result.append(InviteSummary(
            id=str(invite.id),
            email=invite.email,
            role_name=role_name,
            status=st,
            created_at=invite.created_at.isoformat(),
            expires_at=invite.expires_at.isoformat(),
            used_at=invite.used_at.isoformat() if invite.used_at else None,
        ))
    return result


@router.get("/users/{user_id}", response_model=AuthUserResponse)
async def get_user(
    user_id: uuid.UUID,
    _: None = Depends(require_permission("users:read")),
    session: AsyncSession = Depends(get_session),
) -> AuthUserResponse:
    """Return a single user by ID."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    await session.refresh(user)
    return _user_response(user)


@router.patch("/users/{user_id}", response_model=AuthUserResponse)
async def patch_user(
    user_id: uuid.UUID,
    payload: PatchUserRequest,
    claims=Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> AuthUserResponse:
    """Update a user's active status or role assignments."""
    if str(user_id) == claims.sub and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot deactivate own account")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role_ids is not None:
        existing = list((await session.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )).scalars().all())
        for ur in existing:
            await session.delete(ur)
        for rid in payload.role_ids:
            session.add(UserRole(user_id=user_id, role_id=rid))
    await session.commit()
    await session.refresh(user)
    return _user_response(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    claims=Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a user account (cannot delete own account)."""
    await _delete_user(session, user_id, claims.sub)


# ---------------------------------------------------------------------------
# Invite endpoint
# ---------------------------------------------------------------------------

@router.post("/users/invite", response_model=InviteResponse)
async def invite_user(
    payload: InviteRequest,
    claims=Depends(require_permission("users:invite")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> InviteResponse:
    """Generate a 48-hour invite token for a prospective user."""
    raw = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    invite = InviteToken(
        email=payload.email,
        token_hash=token_hash,
        raw_token=raw,
        role_id=payload.role_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    session.add(invite)
    await session.commit()
    base = await _resolve_admin_url(session, settings)
    invite_url = f"{base.rstrip('/')}/accept-invite?token={raw}" if base else None

    if invite_url:
        try:
            await send_invite(settings, to=payload.email, invite_url=invite_url)
        except Exception:
            logger.exception("failed to send invite email to %s", payload.email)

    return InviteResponse(token=raw, invite_url=invite_url)


# ---------------------------------------------------------------------------
# Invite copy-link endpoint (returns existing URL without regenerating)
# ---------------------------------------------------------------------------

@router.get("/users/invites/{invite_id}/link", response_model=InviteResponse)
async def get_invite_link(
    invite_id: uuid.UUID,
    _: object = Depends(require_permission("users:invite")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> InviteResponse:
    """Return the existing invite URL without generating a new token.

    Falls back to silent regeneration (no email) for older invites that
    predate the raw_token column.
    """
    result = await session.execute(select(InviteToken).where(InviteToken.id == invite_id))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")

    if invite.raw_token:
        base = await _resolve_admin_url(session, settings)
        invite_url = f"{base.rstrip('/')}/accept-invite?token={invite.raw_token}" if base else None
        return InviteResponse(token=invite.raw_token, invite_url=invite_url)

    # Legacy invite without stored raw_token — silently regenerate, no email.
    email = invite.email
    role_id = invite.role_id
    await session.delete(invite)
    raw = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    session.add(InviteToken(
        email=email,
        token_hash=token_hash,
        raw_token=raw,
        role_id=role_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    ))
    await session.commit()
    base = await _resolve_admin_url(session, settings)
    invite_url = f"{base.rstrip('/')}/accept-invite?token={raw}" if base else None
    return InviteResponse(token=raw, invite_url=invite_url)


# ---------------------------------------------------------------------------
# Invite regenerate endpoint
# ---------------------------------------------------------------------------

@router.post("/users/invites/{invite_id}/regenerate", response_model=InviteResponse)
async def regenerate_invite(
    invite_id: uuid.UUID,
    _: object = Depends(require_permission("users:invite")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> InviteResponse:
    """Replace an existing invite with a fresh 48-hour token and resend the email."""
    result = await session.execute(select(InviteToken).where(InviteToken.id == invite_id))
    old = result.scalar_one_or_none()
    if old is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")
    email = old.email
    role_id = old.role_id
    await session.delete(old)
    raw = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    new_invite = InviteToken(
        email=email,
        token_hash=token_hash,
        raw_token=raw,
        role_id=role_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    session.add(new_invite)
    await session.commit()
    base = await _resolve_admin_url(session, settings)
    invite_url = f"{base.rstrip('/')}/accept-invite?token={raw}" if base else None

    if invite_url:
        try:
            await send_invite(settings, to=email, invite_url=invite_url)
        except Exception:
            logger.exception("failed to resend invite email to %s", email)

    return InviteResponse(token=raw, invite_url=invite_url)


# ---------------------------------------------------------------------------
# Role endpoints
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleSummary])
async def list_roles(
    _: None = Depends(require_permission("users:read")),
    session: AsyncSession = Depends(get_session),
) -> list[RoleSummary]:
    """List all roles with their permission sets."""
    roles = await _list_roles(session)
    return [
        RoleSummary(
            id=r.id,
            name=r.name,
            description=r.description,
            is_system=r.is_system,
            permissions=[rp.permission for rp in r.permissions],
        )
        for r in roles
    ]


@router.post("/roles", status_code=status.HTTP_201_CREATED, response_model=RoleSummary)
async def create_role(
    payload: CreateRoleRequest,
    _: None = Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> RoleSummary:
    """Create a new custom role."""
    role = Role(name=payload.name, description=payload.description)
    session.add(role)
    await session.flush()
    for perm in payload.permissions:
        session.add(RolePermission(role_id=role.id, permission=perm))
    await session.commit()
    await session.refresh(role)
    return RoleSummary(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=[rp.permission for rp in role.permissions],
    )


@router.patch("/roles/{role_id}", response_model=RoleSummary)
async def patch_role(
    role_id: uuid.UUID,
    payload: PatchRoleRequest,
    _: None = Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> RoleSummary:
    """Update a role's description or permissions (cannot rename system roles)."""
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
    if payload.description is not None:
        role.description = payload.description
    if payload.permissions is not None:
        existing = list((await session.execute(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )).scalars().all())
        for rp in existing:
            await session.delete(rp)
        for perm in payload.permissions:
            session.add(RolePermission(role_id=role_id, permission=perm))
    await session.commit()
    await session.refresh(role)
    return RoleSummary(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=[rp.permission for rp in role.permissions],
    )


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    _: None = Depends(require_permission("users:write")),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a custom role (system roles cannot be deleted)."""
    role = await session.get(Role, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot delete system role")
    await session.delete(role)
    await session.commit()

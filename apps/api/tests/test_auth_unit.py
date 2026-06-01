"""Unit tests for app/auth/* — no database, no HTTP."""

from __future__ import annotations

import time

import pytest
from app.auth.jwt import UserClaims, create_access_token, verify_jwt
from app.auth.password import hash_password, verify_password
from app.auth.permissions import resolve_permissions


# ---------------------------------------------------------------------------
# password
# ---------------------------------------------------------------------------

def test_hash_and_verify_roundtrip() -> None:
    """verify_password accepts the hash produced by hash_password."""
    pw = "correct-horse-battery-staple"
    assert verify_password(pw, hash_password(pw))


def test_wrong_password_rejected() -> None:
    """verify_password rejects an incorrect password."""
    h = hash_password("correct")
    assert not verify_password("wrong", h)


# ---------------------------------------------------------------------------
# jwt
# ---------------------------------------------------------------------------

def test_access_token_roundtrip() -> None:
    """verify_jwt decodes a freshly created token and returns the same claims."""
    claims = UserClaims(
        sub="user-uuid-123",
        email="a@b.com",
        roles=["admin"],
        permissions=["plugins:read"],
    )
    secret = "test-secret"
    token = create_access_token(claims, secret=secret, ttl_seconds=300)
    decoded = verify_jwt(token, secret=secret)
    assert decoded.sub == "user-uuid-123"
    assert decoded.email == "a@b.com"
    assert decoded.permissions == ["plugins:read"]


def test_expired_token_raises() -> None:
    """verify_jwt raises HTTPException 401 for an expired token."""
    from fastapi import HTTPException
    claims = UserClaims(sub="x", email="x@y.com", roles=[], permissions=[])
    token = create_access_token(claims, secret="s", ttl_seconds=0)
    time.sleep(1)
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt(token, secret="s")
    assert exc_info.value.status_code == 401


def test_invalid_token_raises() -> None:
    """verify_jwt raises HTTPException 401 for a garbage string."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        verify_jwt("not.a.token", secret="s")
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------

def test_resolve_permissions_union_of_roles() -> None:
    """Permissions from two roles are unioned."""
    role_perms = [["plugins:read", "metrics:read"], ["settings:read"]]
    overrides: list[tuple[str, bool]] = []
    result = resolve_permissions(role_perms, overrides)
    assert result == {"plugins:read", "metrics:read", "settings:read"}


def test_resolve_permissions_grant_override_adds() -> None:
    """A granted user_permission adds a perm not in any role."""
    result = resolve_permissions([[]], [("plugins:write", True)])
    assert "plugins:write" in result


def test_resolve_permissions_deny_override_removes() -> None:
    """A denied user_permission removes a perm even if a role grants it."""
    result = resolve_permissions([["plugins:read"]], [("plugins:read", False)])
    assert "plugins:read" not in result

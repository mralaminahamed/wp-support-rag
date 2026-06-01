"""JWT creation and verification for HTTP-only cookie sessions.

Access tokens are short-lived JWTs (HS256) whose payload embeds the user's
effective permission set so route dependencies need no DB lookup per request.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from jose import JWTError, jwt


@dataclass
class UserClaims:
    """Decoded claims extracted from a valid access token.

    Attributes:
        sub: User UUID as a string.
        email: User email address.
        roles: Role names held by the user.
        permissions: Effective permission strings embedded at login time.
    """

    sub: str
    email: str
    roles: list[str]
    permissions: list[str] = field(default_factory=list)


def create_access_token(
    claims: UserClaims,
    *,
    secret: str,
    ttl_seconds: int,
) -> str:
    """Encode a signed JWT containing the user's identity and permissions.

    Args:
        claims: The user identity and permission set to embed.
        secret: The HS256 signing secret.
        ttl_seconds: Lifetime in seconds from now.

    Returns:
        str: The encoded JWT string.
    """
    payload = {
        "sub": claims.sub,
        "email": claims.email,
        "roles": claims.roles,
        "permissions": claims.permissions,
        "exp": int(time.time()) + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_jwt(token: str, *, secret: str) -> UserClaims:
    """Decode and validate a JWT, returning the embedded claims.

    Args:
        token: The encoded JWT string from the cookie.
        secret: The HS256 signing secret.

    Returns:
        UserClaims: The decoded claims.

    Raises:
        HTTPException: 401 when the token is missing, expired, or invalid.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from exc
    return UserClaims(
        sub=payload["sub"],
        email=payload["email"],
        roles=payload.get("roles", []),
        permissions=payload.get("permissions", []),
    )

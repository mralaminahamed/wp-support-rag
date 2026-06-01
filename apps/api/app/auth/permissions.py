"""Permission resolution: union of role perms with per-user overrides.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

ALL_PERMISSIONS: frozenset[str] = frozenset(
    (
        "plugins:read",
        "plugins:write",
        "ingestion:trigger",
        "metrics:read",
        "settings:read",
        "settings:write",
        "users:read",
        "users:write",
        "users:invite",
    )
)


def resolve_permissions(
    role_permission_lists: list[list[str]],
    user_overrides: list[tuple[str, bool]],
) -> set[str]:
    """Compute the effective permission set for a user.

    Unions all role permissions then applies per-user overrides: granted=True
    adds a permission, granted=False removes it even if a role grants it.

    Args:
        role_permission_lists: One list of permission strings per role held.
        user_overrides: (permission, granted) pairs from user_permissions table.

    Returns:
        set[str]: The effective permission set.
    """
    effective: set[str] = set()
    for perms in role_permission_lists:
        effective.update(perms)
    for permission, granted in user_overrides:
        if granted:
            effective.add(permission)
        else:
            effective.discard(permission)
    return effective

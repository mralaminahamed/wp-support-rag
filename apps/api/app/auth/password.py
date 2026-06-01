"""Password hashing and verification using bcrypt.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Return the bcrypt hash of a plain-text password.

    Args:
        plain: The plain-text password.

    Returns:
        str: The bcrypt hash string.
    """
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash.

    Args:
        plain: The plain-text password to verify.
        hashed: The stored bcrypt hash.

    Returns:
        bool: True when the password is correct.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())

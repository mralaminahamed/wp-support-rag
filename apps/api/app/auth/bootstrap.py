"""First-boot admin seeding.

If no users exist and WPRAG_BOOTSTRAP_EMAIL + WPRAG_BOOTSTRAP_PASSWORD are
configured, creates one super_admin user. Runs once per process start; the
guard is the users-table row count, not a flag, so it is idempotent.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.config import Settings
from app.db.models import Role, User, UserRole

logger = logging.getLogger(__name__)


async def maybe_bootstrap_admin(session: AsyncSession, settings: Settings) -> None:
    """Seed the first super_admin user if none exist.

    No-ops when users already exist or when bootstrap credentials are not
    configured. Safe to call on every startup.

    Args:
        session: An open async database session.
        settings: Application settings supplying bootstrap credentials.
    """
    if not settings.bootstrap_email or not settings.bootstrap_password:
        return

    count = (await session.execute(text("SELECT COUNT(*) FROM users"))).scalar_one()
    if count > 0:
        return

    logger.info("bootstrapping first super_admin user", extra={"email": settings.bootstrap_email})

    super_admin = (
        await session.execute(select(Role).where(Role.name == "super_admin"))
    ).scalar_one_or_none()
    if super_admin is None:
        logger.warning("super_admin role not found; skipping bootstrap")
        return

    user = User(
        email=settings.bootstrap_email,
        password_hash=hash_password(settings.bootstrap_password.get_secret_value()),
        is_active=True,
    )
    session.add(user)
    await session.flush()

    session.add(UserRole(user_id=user.id, role_id=super_admin.id))
    await session.commit()
    logger.info("bootstrap complete — super_admin user created")

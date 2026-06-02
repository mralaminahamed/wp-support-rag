"""Setup wizard endpoints — first-run status and completion.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_any_admin, require_permission
from app.api.schemas import SetupStatusResponse
from app.auth.jwt import UserClaims
from app.db.engine import get_session
from app.db.models import SystemSetting

router = APIRouter(prefix="/api/v1/admin", tags=["setup"])

_KEY = "setup_complete"


@router.get("/setup/status", response_model=SetupStatusResponse)
async def get_setup_status(
    _: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Return whether the first-run setup wizard has been completed.

    Returns ``complete: false`` when the ``setup_complete`` key is absent or
    not ``"true"``, so a missing row is treated as incomplete.
    """
    row = await session.scalar(
        select(SystemSetting).where(SystemSetting.key == _KEY)
    )
    return SetupStatusResponse(complete=row is not None and row.value == "true")


@router.post("/setup/complete", response_model=SetupStatusResponse)
async def complete_setup(
    _: UserClaims = Depends(require_permission("settings:write")),
    session: AsyncSession = Depends(get_session),
) -> SetupStatusResponse:
    """Mark the first-run setup wizard as complete.

    Upserts the ``setup_complete`` system setting so the call is idempotent.
    """
    stmt = (
        pg_insert(SystemSetting)
        .values(key=_KEY, value="true")
        .on_conflict_do_update(index_elements=["key"], set_={"value": "true"})
    )
    await session.execute(stmt)
    await session.commit()
    return SetupStatusResponse(complete=True)

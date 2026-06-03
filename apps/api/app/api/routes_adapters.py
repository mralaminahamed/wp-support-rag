"""Adapter-plugin management endpoints.

Exposes CRUD operations for adapter plugins: list installed adapters, list
available source types, upload a new file-based adapter, and delete a
file-based adapter. All endpoints require admin authentication.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.engine import get_session
from app.api.schemas import AdapterPluginSummary
from app.config import get_settings
from app.db.models import AdapterPlugin
from app.ingestion.adapter_registry import AdapterTypeInfo, _is_valid_adapter, get_registry

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["adapters"])


@router.get("/adapter-plugins", response_model=list[AdapterPluginSummary])
async def list_adapter_plugins(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:read")),
) -> list[AdapterPlugin]:
    """Return all installed adapter plugins ordered by installation date.

    Args:
        session: Database session.
        _: Auth guard (requires ``settings:read`` permission).

    Returns:
        list[AdapterPlugin]: All adapter-plugin rows, ordered by installed_at ASC.
    """
    result = await session.execute(
        select(AdapterPlugin).order_by(AdapterPlugin.installed_at)
    )
    return list(result.scalars().all())


@router.get("/adapter-plugins/types", response_model=list[AdapterTypeInfo])
async def list_adapter_types(
    _: object = Depends(require_permission("settings:read")),
) -> list[AdapterTypeInfo]:
    """Return all registered source types from the live in-process registry.

    Does not hit the database; returns the in-memory view built at startup.

    Args:
        _: Auth guard (requires ``settings:read`` permission).

    Returns:
        list[AdapterTypeInfo]: Ordered list of all registered source types.
    """
    return get_registry().types_with_schema()


@router.post("/adapter-plugins/upload", response_model=AdapterPluginSummary)
async def upload_adapter_plugin(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:write")),
) -> AdapterPlugin:
    """Upload and install a Python file-based adapter plugin.

    Validates the file extension, checks for type conflicts with already-loaded
    adapters, saves the file to ``custom_adapters_dir``, and attempts to import
    and validate the module. On success, upserts a ``status='loaded'`` DB row;
    on import/validation failure, upserts ``status='error'``.

    Args:
        file: The uploaded ``.py`` file.
        session: Database session.
        _: Auth guard (requires ``settings:write`` permission).

    Returns:
        AdapterPlugin: The upserted adapter-plugin row.

    Raises:
        HTTPException: 422 if the file extension is not ``.py``.
        HTTPException: 409 if any claimed source type is already owned by a loaded adapter.
    """
    filename = file.filename or ""
    if not filename.endswith(".py"):
        raise HTTPException(
            status_code=422,
            detail="only .py files are accepted",
        )

    settings = get_settings()
    custom_dir = Path(settings.custom_adapters_dir)
    custom_dir.mkdir(parents=True, exist_ok=True)

    content = await file.read()

    # Determine slug based on stem and first valid class found (used for conflict check)
    stem = Path(filename).stem
    dest_path = custom_dir / filename

    # Try to detect handles claimed by this file before saving, for conflict detection.
    # We do a quick parse by importing from bytes in a temp module name.
    claimed_handles: list[str] = []
    first_class_name: str | None = None

    try:
        module_name = f"_upload_probe_{stem}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        import types
        probe_module = types.ModuleType(module_name)
        exec(compile(content, filename, "exec"), probe_module.__dict__)  # noqa: S102

        for _attr_name, obj in inspect.getmembers(probe_module, inspect.isclass):
            if not _is_valid_adapter(obj):
                continue
            if first_class_name is None:
                first_class_name = obj.__name__
            claimed_handles.extend(list(obj.handles))
    except Exception:
        # If we can't probe, we'll let the import-and-validate step handle it
        claimed_handles = []
        first_class_name = None

    # 409 check: any claimed handle already loaded by another adapter?
    if claimed_handles:
        existing_stmt = select(AdapterPlugin).where(
            AdapterPlugin.status == "loaded",
            AdapterPlugin.handles.overlap(claimed_handles),
        )
        existing_result = await session.execute(existing_stmt)
        conflicting = existing_result.scalars().all()
        # Filter out rows with the same slug (self-update is OK)
        slug_for_check = f"file.{stem}.{first_class_name}" if first_class_name else None
        conflicts = [row for row in conflicting if row.slug != slug_for_check]
        if conflicts:
            conflict_types = [h for row in conflicts for h in row.handles if h in claimed_handles]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"source types already claimed by loaded adapter: {conflict_types}",
            )

    # Save file to disk (overwrite OK)
    dest_path.write_bytes(content)

    # Now import and validate for real
    module_name_real = f"_custom_adapter_{stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name_real, dest_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not create module spec for {dest_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        # Import failed — upsert error row and return
        error_slug = f"file.{stem}.unknown"
        row = await _upsert_adapter_row(
            session,
            slug=error_slug,
            display_name=stem,
            filename=filename,
            handles=[],
            config_schema={},
            status="error",
            error=str(exc),
        )
        return row

    # Find valid adapter classes in the loaded module
    valid_classes: list[type] = []
    for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
        if not _is_valid_adapter(obj):
            continue
        valid_classes.append(obj)

    if not valid_classes:
        error_slug = f"file.{stem}.unknown"
        row = await _upsert_adapter_row(
            session,
            slug=error_slug,
            display_name=stem,
            filename=filename,
            handles=[],
            config_schema={},
            status="error",
            error="no valid adapter class found (needs handles tuple and fetch method)",
        )
        return row

    # Use the first valid class
    adapter_class = valid_classes[0]
    slug = f"file.{stem}.{adapter_class.__name__}"
    handles = list(adapter_class.handles)
    display_name = getattr(adapter_class, "display_name", adapter_class.__name__)
    config_schema = getattr(adapter_class, "config_schema", {})

    row = await _upsert_adapter_row(
        session,
        slug=slug,
        display_name=display_name,
        filename=filename,
        handles=handles,
        config_schema=config_schema,
        status="loaded",
        error=None,
    )
    return row


@router.delete("/adapter-plugins/{slug:path}", status_code=204)
async def delete_adapter_plugin(
    slug: str,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("settings:write")),
) -> None:
    """Delete a file-based adapter plugin.

    Only adapters with ``source='file'`` may be deleted. Removes both the file
    from ``custom_adapters_dir`` and the DB row.

    Args:
        slug: The unique adapter slug (path parameter, supports dots and slashes).
        session: Database session.
        _: Auth guard (requires ``settings:write`` permission).

    Raises:
        HTTPException: 404 if the adapter slug is not found.
        HTTPException: 403 if the adapter is not file-based (e.g. builtin).
    """
    row = (
        await session.execute(
            select(AdapterPlugin).where(AdapterPlugin.slug == slug)
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="adapter plugin not found",
        )

    if row.source != "file":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only file-based adapter plugins can be deleted",
        )

    # Delete the file from disk if it exists
    if row.filename:
        settings = get_settings()
        file_path = Path(settings.custom_adapters_dir) / row.filename
        if file_path.exists():
            file_path.unlink()

    await session.delete(row)
    await session.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _upsert_adapter_row(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
    filename: str,
    handles: list[str],
    config_schema: dict,
    status: str,
    error: str | None,
) -> AdapterPlugin:
    """Upsert a row in ``adapter_plugins`` and return the refreshed ORM object.

    Args:
        session: Database session (caller is responsible for scope).
        slug: Unique adapter slug.
        display_name: Human-readable name.
        filename: Source filename.
        handles: List of handled source-type strings.
        config_schema: JSON Schema dict.
        status: ``"loaded"`` or ``"error"``.
        error: Error message when status is ``"error"``.

    Returns:
        AdapterPlugin: The upserted row, refreshed from the database.
    """
    row_data: dict = {
        "slug": slug,
        "display_name": display_name,
        "source": "file",
        "entry_point": None,
        "filename": filename,
        "handles": handles,
        "config_schema": config_schema,
        "status": status,
        "error": error,
    }
    stmt = (
        pg_insert(AdapterPlugin)
        .values(**row_data)
        .on_conflict_do_update(
            index_elements=["slug"],
            set_=row_data,
        )
        .returning(AdapterPlugin)
    )
    result = await session.execute(stmt)
    await session.commit()

    # Fetch the row fresh so ORM instance is properly loaded
    slug_val = slug
    fetched = (
        await session.execute(
            select(AdapterPlugin).where(AdapterPlugin.slug == slug_val)
        )
    ).scalar_one()
    return fetched

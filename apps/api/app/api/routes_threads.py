"""Playground conversation-thread endpoints.

Authenticated routes for creating, listing, and deleting threads plus
appending and reading their messages. Admins with threads:read_all see every
user's threads; others see only their own.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_any_admin
from app.api.schemas import (
    AppendMessagesRequest,
    CreateThreadRequest,
    ThreadMessageItem,
    ThreadSummary,
)
from app.auth.jwt import UserClaims
from app.db.engine import get_session
from app.db.models import ConversationThread, ThreadMessage, User

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


def _thread_to_summary(t: ConversationThread, owner_email: str | None = None) -> ThreadSummary:
    return ThreadSummary(
        id=t.id,
        title=t.title,
        plugin_slug=t.plugin_slug,
        created_at=t.created_at.isoformat(),
        updated_at=t.updated_at.isoformat(),
        owner_email=owner_email,
    )


def _message_to_item(m: ThreadMessage) -> ThreadMessageItem:
    return ThreadMessageItem(
        id=m.id,
        role=m.role,
        content=m.content,
        query_id=m.query_id,
        meta=m.meta,
        created_at=m.created_at.isoformat(),
    )


async def _get_thread_or_404(
    session: AsyncSession,
    thread_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    is_admin: bool = False,
) -> ConversationThread:
    q = select(ConversationThread).where(ConversationThread.id == thread_id)
    if not is_admin:
        q = q.where(ConversationThread.user_id == user_id)
    thread = (await session.execute(q)).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    return thread


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    claims: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadSummary]:
    """Return threads: all (with owner_email) for admins, own only for others."""
    is_admin = "threads:read_all" in claims.permissions

    if is_admin:
        rows = (
            await session.execute(
                select(ConversationThread, User.email.label("owner_email"))
                .join(User, User.id == ConversationThread.user_id)
                .order_by(ConversationThread.updated_at.desc())
                .limit(500)
            )
        ).all()
        return [_thread_to_summary(t, email) for t, email in rows]

    rows = (
        await session.execute(
            select(ConversationThread)
            .where(ConversationThread.user_id == claims.sub)
            .order_by(ConversationThread.updated_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return [_thread_to_summary(t) for t in rows]


@router.post("", response_model=ThreadSummary, status_code=status.HTTP_201_CREATED)
async def create_thread(
    body: CreateThreadRequest,
    claims: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> ThreadSummary:
    """Create a new conversation thread owned by the authenticated user."""
    thread = ConversationThread(
        user_id=claims.sub,
        title=body.title,
        plugin_slug=body.plugin_slug,
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return _thread_to_summary(thread)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID,
    claims: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a thread. Admins can delete any thread; others only their own."""
    is_admin = "threads:read_all" in claims.permissions
    thread = await _get_thread_or_404(session, thread_id, claims.sub, is_admin=is_admin)
    await session.delete(thread)
    await session.commit()


@router.get("/{thread_id}/messages", response_model=list[ThreadMessageItem])
async def get_thread_messages(
    thread_id: uuid.UUID,
    claims: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadMessageItem]:
    """Return all messages in a thread in chronological order."""
    is_admin = "threads:read_all" in claims.permissions
    await _get_thread_or_404(session, thread_id, claims.sub, is_admin=is_admin)
    rows = (
        await session.execute(
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread_id)
            .order_by(ThreadMessage.created_at)
        )
    ).scalars().all()
    return [_message_to_item(m) for m in rows]


@router.post("/{thread_id}/messages", response_model=list[ThreadMessageItem], status_code=status.HTTP_201_CREATED)
async def append_messages(
    thread_id: uuid.UUID,
    body: AppendMessagesRequest,
    claims: UserClaims = Depends(require_any_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ThreadMessageItem]:
    """Append one or more messages to a thread and bump updated_at."""
    from sqlalchemy import text as sqla_text

    is_admin = "threads:read_all" in claims.permissions
    thread = await _get_thread_or_404(session, thread_id, claims.sub, is_admin=is_admin)
    created: list[ThreadMessage] = []
    for item in body.messages:
        msg = ThreadMessage(
            thread_id=thread.id,
            role=item.role,
            content=item.content,
            query_id=item.query_id,
            meta=item.meta,
        )
        session.add(msg)
        created.append(msg)

    await session.execute(
        sqla_text("UPDATE conversation_threads SET updated_at = now() WHERE id = :id"),
        {"id": str(thread_id)},
    )
    await session.commit()
    for msg in created:
        await session.refresh(msg)
    return [_message_to_item(m) for m in created]

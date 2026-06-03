"""Support ticket browse and reply endpoints.

Tickets are WP.org support forum threads ingested as documents with
doc_type='wporg_support'. The detail view fetches live replies from the
WP.org REST API; posting replies uses stored WP.org credentials.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import base64
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_settings_dep, require_permission
from app.api.schemas import (
    PostReplyRequest,
    PostReplyResponse,
    TicketDetail,
    TicketReply,
    TicketSummary,
    WporgCredentialsRequest,
    WporgCredentialsResponse,
)
from app.config import Settings
from app.db.engine import get_session
from app.db.models import Chunk, Document, Plugin, SystemSetting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/tickets", tags=["tickets"])

_USERNAME_KEY = "wporg_username"
_PASSWORD_KEY = "wporg_app_password"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_wporg_creds(session: AsyncSession) -> tuple[str | None, str | None]:
    rows = list(
        (
            await session.execute(
                select(SystemSetting).where(
                    SystemSetting.key.in_([_USERNAME_KEY, _PASSWORD_KEY])
                )
            )
        )
        .scalars()
        .all()
    )
    d = {r.key: r.value for r in rows}
    return d.get(_USERNAME_KEY), d.get(_PASSWORD_KEY)


async def _fetch_replies_live(
    source_url: str, settings: Settings
) -> tuple[list[TicketReply], int | None, str | None]:
    """Return (replies, wporg_topic_id, error). Reads from WP.org REST API."""
    topic_slug = source_url.rstrip("/").rsplit("/", 1)[-1]
    api_base = f"{settings.wporg_site_url.rstrip('/')}/support/wp-json/wp/v2"
    replies: list[TicketReply] = []
    topic_id: int | None = None

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # 1. Resolve topic by slug → get topic_id and first post
            r = await client.get(
                f"{api_base}/topics",
                params={"slug": topic_slug, "_embed": "author", "per_page": 1},
                headers={"Accept": "application/json"},
            )
            if r.status_code != 200:
                return [], None, f"WP.org topics endpoint returned {r.status_code}"
            data = r.json()
            if not data:
                return [], None, "topic not found on WP.org"
            topic = data[0]
            topic_id = int(topic["id"])
            author_embed = ((topic.get("_embedded") or {}).get("author") or [{}])[0]
            replies.append(
                TicketReply(
                    id=topic_id,
                    author=author_embed.get("name", "Unknown"),
                    author_url=author_embed.get("link"),
                    content=(topic.get("content") or {}).get("rendered", ""),
                    created_at=topic.get("date", ""),
                    is_topic=True,
                )
            )

            # 2. Paginate replies
            page = 1
            while True:
                rr = await client.get(
                    f"{api_base}/replies",
                    params={
                        "topic": topic_id,
                        "per_page": 100,
                        "page": page,
                        "_embed": "author",
                        "orderby": "date",
                        "order": "asc",
                    },
                    headers={"Accept": "application/json"},
                )
                if rr.status_code == 400 or rr.status_code == 404:
                    break
                if rr.status_code != 200:
                    break
                batch = rr.json()
                if not batch:
                    break
                for rep in batch:
                    a = ((rep.get("_embedded") or {}).get("author") or [{}])[0]
                    replies.append(
                        TicketReply(
                            id=int(rep["id"]),
                            author=a.get("name", "Unknown"),
                            author_url=a.get("link"),
                            content=(rep.get("content") or {}).get("rendered", ""),
                            created_at=rep.get("date", ""),
                            is_topic=False,
                        )
                    )
                total_pages = int(rr.headers.get("X-WP-TotalPages", 1))
                if page >= total_pages:
                    break
                page += 1

    except Exception as exc:
        logger.warning("live fetch failed for %s: %s", source_url, exc)
        return replies, topic_id, str(exc)

    return replies, topic_id, None


# ---------------------------------------------------------------------------
# Credential endpoints
# ---------------------------------------------------------------------------


@router.get("/credentials", response_model=WporgCredentialsResponse)
async def get_credentials(
    _: None = Depends(require_permission("plugins:read")),
    session: AsyncSession = Depends(get_session),
) -> WporgCredentialsResponse:
    """Return whether WP.org posting credentials are configured."""
    username, password = await _get_wporg_creds(session)
    return WporgCredentialsResponse(
        configured=bool(username and password), username=username
    )


@router.put("/credentials", response_model=WporgCredentialsResponse)
async def save_credentials(
    payload: WporgCredentialsRequest,
    _: None = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
) -> WporgCredentialsResponse:
    """Store WP.org username + application password for reply posting."""
    for key, value in [
        (_USERNAME_KEY, payload.username),
        (_PASSWORD_KEY, payload.app_password),
    ]:
        row = await session.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if row:
            row.value = value
        else:
            session.add(SystemSetting(key=key, value=value))
    await session.commit()
    return WporgCredentialsResponse(configured=True, username=payload.username)


# ---------------------------------------------------------------------------
# Ticket list / detail
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TicketSummary])
async def list_tickets(
    _: None = Depends(require_permission("plugins:read")),
    session: AsyncSession = Depends(get_session),
) -> list[TicketSummary]:
    """List all ingested WP.org support tickets."""
    rows = (
        await session.execute(
            select(
                Document,
                Plugin.slug.label("plugin_slug"),
                func.count(Chunk.id).label("chunk_count"),
            )
            .join(Plugin, Plugin.id == Document.plugin_id)
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .where(Document.doc_type == "wporg_support")
            .group_by(Document.id, Plugin.slug)
            .order_by(Document.fetched_at.desc())
        )
    ).all()
    return [
        TicketSummary(
            id=str(doc.id),
            title=doc.title or doc.external_id,
            source_url=doc.source_url,
            plugin_slug=plugin_slug,
            fetched_at=doc.fetched_at.isoformat(),
            chunk_count=chunk_count,
            creator=(doc.meta or {}).get("creator"),
            reply_count=(doc.meta or {}).get("reply_count"),
            participant_count=(doc.meta or {}).get("participant_count"),
            last_reply_at=(doc.meta or {}).get("last_reply_at"),
        )
        for doc, plugin_slug, chunk_count in rows
    ]


@router.get("/{doc_id}", response_model=TicketDetail)
async def get_ticket(
    doc_id: uuid.UUID,
    _: None = Depends(require_permission("plugins:read")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> TicketDetail:
    """Fetch a ticket with live replies from WP.org."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ticket not found")
    plugin = await session.get(Plugin, doc.plugin_id)
    plugin_slug = plugin.slug if plugin else "unknown"

    replies, topic_id, error = await _fetch_replies_live(doc.source_url, settings)

    return TicketDetail(
        id=str(doc.id),
        title=doc.title or doc.external_id,
        source_url=doc.source_url,
        plugin_slug=plugin_slug,
        replies=replies,
        wporg_topic_id=topic_id,
        error=error,
    )


# ---------------------------------------------------------------------------
# Post reply
# ---------------------------------------------------------------------------


@router.post("/{doc_id}/replies", response_model=PostReplyResponse)
async def post_reply(
    doc_id: uuid.UUID,
    payload: PostReplyRequest,
    _: None = Depends(require_permission("plugins:write")),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> PostReplyResponse:
    """Post a reply to a WP.org support ticket via the REST API."""
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ticket not found")

    username, app_password = await _get_wporg_creds(session)
    if not username or not app_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="WP.org credentials not configured — set them in the Tickets settings.",
        )

    topic_slug = doc.source_url.rstrip("/").rsplit("/", 1)[-1]
    api_base = f"{settings.wporg_site_url.rstrip('/')}/support/wp-json/wp/v2"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(
            f"{api_base}/topics",
            params={"slug": topic_slug, "per_page": 1},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200 or not r.json():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="topic not found on WP.org",
            )
        topic_id = r.json()[0]["id"]

        creds = base64.b64encode(f"{username}:{app_password}".encode()).decode()
        r2 = await client.post(
            f"{api_base}/replies",
            json={"topic": topic_id, "content": payload.content, "status": "publish"},
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {creds}",
            },
        )
        if r2.status_code in (200, 201):
            return PostReplyResponse(
                success=True,
                message="Reply posted to WordPress.org.",
                reply_url=r2.json().get("link"),
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WP.org returned {r2.status_code}: {r2.text[:300]}",
        )

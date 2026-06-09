"""Support ticket browse and reply endpoints.

Tickets are WP.org support forum threads ingested as documents with
doc_type='wporg_support'. The detail view fetches live replies by scraping
the WP.org support thread HTML (the forum uses bbPress which does not expose
a public REST API for topics/replies on wordpress.org).

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

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

_WPORG_DATE_RE = re.compile(r"(\w+ \d+, \d{4}) at (\d+:\d+ (?:am|pm))", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_wporg_date(raw: str) -> str:
    """Parse 'May 17, 2026 at 6:11 am' → ISO datetime string."""
    m = _WPORG_DATE_RE.search(raw.strip())
    if not m:
        return raw
    try:
        dt = datetime.strptime(f"{m.group(1)} {m.group(2).upper()}", "%B %d, %Y %I:%M %p")
        return dt.isoformat()
    except ValueError:
        return raw


def _parse_thread_page(
    html: str, is_first: bool
) -> tuple[list[TicketReply], int | None, str | None]:
    """Parse one HTML page of a WP.org support thread.

    Extracts the topic post (first page only), all reply posts, the WP.org
    internal topic ID, and the URL of the next page (if paginated).

    Returns:
        (replies, topic_id, next_page_url)
    """
    replies: list[TicketReply] = []

    # Numeric topic ID from the replies list element id="topic-NNN-replies"
    topic_id: int | None = None
    tid_m = re.search(r'id="topic-(\d+)-replies"', html)
    if tid_m:
        topic_id = int(tid_m.group(1))

    # Next page link — bbPress renders: <a class="next page-numbers" href="...">
    next_url: str | None = None
    npm = re.search(r'class="next page-numbers" href="([^"]+)"', html)
    if not npm:
        npm = re.search(r'href="([^"]+)"[^>]*class="next page-numbers"', html)
    if npm:
        next_url = npm.group(1).replace("&#038;", "&")

    # ── Topic post (first page only) ────────────────────────────────────────
    if is_first:
        am = re.search(
            r'class="bbp-topic-author".*?'
            r'href="(https://wordpress\.org/support/users/[^"]+)"[^>]*>.*?'
            r'class="bbp-author-name"[^>]*>([^<]+)</span>.*?'
            r'title="([^"]+)"[^>]*class="bbp-topic-permalink"',
            html,
            re.DOTALL,
        )
        cm = re.search(
            r'<div class="bbp-topic-content">(.*?)</div><!-- \.bbp-topic-content -->',
            html,
            re.DOTALL,
        )
        if cm:
            author_url = am.group(1) if am else None
            author = am.group(2).strip() if am else "Unknown"
            date = _parse_wporg_date(am.group(3)) if am else ""
            post_id = topic_id or 0
            # Use the actual topic post div id when available
            tdm = re.search(r'id="post-(\d+)"[^>]*type-topic', html)
            if tdm:
                post_id = int(tdm.group(1))
            replies.append(
                TicketReply(
                    id=post_id,
                    author=author,
                    author_url=author_url,
                    content=cm.group(1).strip(),
                    created_at=date,
                    is_topic=True,
                )
            )

    # ── Reply posts ──────────────────────────────────────────────────────────
    for pm in re.finditer(r'<div id="post-(\d+)"[^>]*type-reply[^>]*>', html):
        post_id = int(pm.group(1))
        block_start = pm.end()
        block_end = html.find(f"<!-- #post-{post_id} -->", block_start)
        if block_end < 0:
            continue
        block = html[block_start:block_end]

        a_m = re.search(
            r'href="(https://wordpress\.org/support/users/[^"]+)"[^>]*>.*?'
            r'class="bbp-author-name"[^>]*>([^<]+)</span>.*?'
            r'title="([^"]+)"[^>]*class="bbp-reply-permalink"',
            block,
            re.DOTALL,
        )
        c_m = re.search(
            r'<div class="bbp-reply-content">(.*?)</div><!-- \.bbp-reply-content -->',
            block,
            re.DOTALL,
        )
        if not c_m:
            continue

        author_url = a_m.group(1) if a_m else None
        author = a_m.group(2).strip() if a_m else "Unknown"
        date = _parse_wporg_date(a_m.group(3)) if a_m else ""

        replies.append(
            TicketReply(
                id=post_id,
                author=author,
                author_url=author_url,
                content=c_m.group(1).strip(),
                created_at=date,
                is_topic=False,
            )
        )

    return replies, topic_id, next_url


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
    """Scrape a WP.org support thread for all replies.

    WP.org's support forum (bbPress) does not expose a public REST API for
    topics or replies, so we scrape the rendered HTML directly. Pagination is
    handled by following ``next page-numbers`` links up to 20 pages.

    Returns:
        (replies, wporg_topic_id, error_message_or_None)
    """
    replies: list[TicketReply] = []
    topic_id: int | None = None

    try:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 (compatible; wp-support-rag/1.0)",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            next_url: str | None = source_url
            is_first = True
            page_count = 0
            while next_url and page_count < 20:
                r = await client.get(next_url, headers=headers)
                if r.status_code != 200:
                    err = f"WP.org returned HTTP {r.status_code}"
                    return replies, topic_id, err
                page_replies, tid, next_url = _parse_thread_page(r.text, is_first)
                if tid is not None:
                    topic_id = tid
                replies.extend(page_replies)
                is_first = False
                page_count += 1
    except Exception as exc:
        logger.warning("reply fetch failed for %s: %s", source_url, exc)
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
    """Fetch a ticket with live replies scraped from WP.org."""
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
    """Post a reply to a WP.org support ticket.

    Note: wordpress.org's support forum (bbPress) does not expose a public REST
    API for posting replies. This endpoint is a placeholder; users should reply
    directly at wordpress.org until an alternative posting method is available.
    """
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ticket not found")

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Posting replies via API is not supported — wordpress.org's support forum "
            "does not expose a public REST API for reply creation. "
            f"Please reply directly at: {doc.source_url}"
        ),
    )

# Author: Al Amin Ahamed
"""Async email delivery via aiosmtplib.

Only sends when WPRAG_SMTP_HOST is configured; silently no-ops otherwise so
dev environments need no mail server.
"""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import Settings

logger = logging.getLogger(__name__)


async def _send(settings: Settings, *, to: str, subject: str, html: str, text: str) -> None:
    if not settings.smtp_host:
        logger.debug("SMTP not configured — skipping email to %s", to)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    password = settings.smtp_password.get_secret_value() if settings.smtp_password else None
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_use_tls,
            username=settings.smtp_user,
            password=password,
        )
        logger.info("email sent to=%s subject=%r", to, subject)
    except Exception:
        logger.exception("failed to send email to=%s subject=%r", to, subject)


async def send_invite(settings: Settings, *, to: str, invite_url: str) -> None:
    """Send an invite link to a prospective user."""
    subject = "You've been invited to WP Support RAG"
    html = f"""\
<p>Hi,</p>
<p>You've been invited to access the <strong>WP Support RAG</strong> admin console.</p>
<p><a href="{invite_url}">Accept invite &amp; set your password</a></p>
<p>This link expires in 48 hours.</p>
<p>If you didn't expect this email, you can ignore it.</p>
"""
    text = (
        f"You've been invited to WP Support RAG.\n\n"
        f"Accept your invite and set a password here:\n{invite_url}\n\n"
        f"This link expires in 48 hours."
    )
    await _send(settings, to=to, subject=subject, html=html, text=text)


async def send_password_reset(settings: Settings, *, to: str, reset_url: str) -> None:
    """Send a password-reset link."""
    subject = "Reset your WP Support RAG password"
    html = f"""\
<p>Hi,</p>
<p>We received a request to reset your <strong>WP Support RAG</strong> password.</p>
<p><a href="{reset_url}">Reset my password</a></p>
<p>This link expires in 1 hour. If you didn't request a reset, ignore this email.</p>
"""
    text = (
        f"Reset your WP Support RAG password:\n{reset_url}\n\n"
        f"This link expires in 1 hour.\n"
        f"If you didn't request this, ignore the email."
    )
    await _send(settings, to=to, subject=subject, html=html, text=text)


async def send_welcome(settings: Settings, *, to: str) -> None:
    """Send a welcome email after a user accepts their invite."""
    subject = "Welcome to WP Support RAG"
    admin_url = settings.admin_url or "your admin console"
    html = f"""\
<p>Hi,</p>
<p>Your <strong>WP Support RAG</strong> account is ready.</p>
<p><a href="{admin_url}">Sign in</a></p>
"""
    text = f"Your WP Support RAG account is ready.\nSign in at: {admin_url}"
    await _send(settings, to=to, subject=subject, html=html, text=text)

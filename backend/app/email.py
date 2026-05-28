"""
Outbound email.

Uses Resend (https://resend.com) if RESEND_API_KEY is set; otherwise falls
back to logging the message to stdout (dev / local mode). The fallback is
how a fresh Folio instance can still issue password-reset links — the
admin reads the URL out of the server logs.

Resend free tier: 100 emails/day, 3,000/month. Plenty for a personal
medical app, even a multi-user one.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

RESEND_API = "https://api.resend.com/emails"
DEFAULT_FROM = os.environ.get("EMAIL_FROM", "Folio <onboarding@resend.dev>")


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
) -> bool:
    """Return True if delivery was at least attempted."""
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        # No provider configured — log the message so an operator can act.
        log.warning("RESEND_API_KEY missing. Email NOT sent. "
                    "Would have sent to=%r subject=%r body=%s",
                    to, subject, body_text or body_html)
        return False

    payload: dict = {
        "from":    DEFAULT_FROM,
        "to":      [to],
        "subject": subject,
        "html":    body_html,
    }
    if body_text:
        payload["text"] = body_text

    try:
        async with httpx.AsyncClient(timeout=15.0) as cl:
            r = await cl.post(
                RESEND_API,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code >= 400:
            log.error("Resend send failed: %s %s", r.status_code, r.text)
            return False
        return True
    except Exception as exc:
        log.error("Resend send raised: %s", exc)
        return False

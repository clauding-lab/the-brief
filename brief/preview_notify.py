"""Preview-ready notifications: Discord webhook + Brevo email.

When the editorial pipeline runs in dry-run with `--write-fixture`, the
result lands at `public/fixtures/<name>.json`. Once main is pushed, that
fixture is reachable at `/preview?fixture=<name>.json` on the production
SPA.

This module sends two pings telling Adnan a draft is ready:
  - Discord — via webhook URL set in `DISCORD_PREVIEW_WEBHOOK_URL` env
  - Email   — via Brevo to `PREVIEW_EMAIL_RECIPIENT` (separate from the
              subscriber list to keep preview drafts out of subscribers'
              inboxes)

Fail-open: any failure here logs a warning; it never crashes a dry-run.
"""
from __future__ import annotations

import html as _html
import json as _stdjson
import logging
import os
import urllib.error
from dataclasses import dataclass
from datetime import date as date_t
from pathlib import Path
from urllib.request import Request, urlopen


_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_PRODUCTION_BASE = "https://thebrief.clauding-lab.com"


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreviewMeta:
    """Minimal context extracted from a written fixture for the ping."""
    fixture_name: str           # bare filename, e.g. "preview-2026-05-28.json"
    brief_date: date_t          # the brief's intended publish date
    issue_no: int | None        # may be None if absent from fixture
    todays_call: str | None     # first paragraph; truncated in the ping body


@dataclass(frozen=True)
class PreviewNotifyResult:
    """Aggregate outcome of the two-channel send."""
    discord_ok: bool
    discord_error: str | None
    email_ok: bool
    email_error: str | None
    preview_url: str


def preview_url(fixture_name: str) -> str:
    """Build the production-reachable preview URL for a fixture filename."""
    return f"{_PRODUCTION_BASE}/preview?fixture={fixture_name}"


def extract_preview_meta(fixture_path: str | os.PathLike[str]) -> PreviewMeta:
    """Read the fixture JSON and extract the fields needed for a ping.

    The fixture is the same shape as a `BriefPayload`: `{brief: {...}, sections: [...]}`.
    Tolerant of missing fields — the ping degrades gracefully.
    """
    p = Path(fixture_path)
    raw = p.read_text(encoding="utf-8")
    data = _stdjson.loads(raw)
    brief = data.get("brief", {}) if isinstance(data, dict) else {}

    raw_date = brief.get("brief_date")
    if isinstance(raw_date, str):
        brief_date = date_t.fromisoformat(raw_date)
    else:
        brief_date = date_t.today()

    raw_call = brief.get("todays_call")
    todays_call = raw_call.strip() if isinstance(raw_call, str) else None

    issue_no = brief.get("issue_no") if isinstance(brief.get("issue_no"), int) else None

    return PreviewMeta(
        fixture_name=p.name,
        brief_date=brief_date,
        issue_no=issue_no,
        todays_call=todays_call,
    )


# ── Discord webhook ───────────────────────────────────────────────────────────


def send_discord_ping(*, webhook_url: str, meta: PreviewMeta) -> str | None:
    """POST a preview-ready message to a Discord webhook.

    Returns None on success, or a short error tag string on failure.
    """
    url = preview_url(meta.fixture_name)

    header = f"**Preview ready — {meta.brief_date.strftime('%a %d %b %Y')}**"
    if meta.issue_no is not None:
        header += f" · No. {meta.issue_no}"

    lines = [header, url]
    if meta.todays_call:
        first_para = meta.todays_call.split("\n\n", 1)[0]
        snippet = first_para if len(first_para) <= 350 else first_para[:347] + "..."
        lines.extend(["", "> " + snippet.replace("\n", "\n> ")])
    lines.append("")
    lines.append(
        "_URL goes live ~90s after main is pushed; manually push "
        "`public/fixtures/*.json` if it hasn't been._"
    )

    payload = {"content": "\n".join(lines)}
    req = Request(
        webhook_url,
        data=_stdjson.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )
    try:
        with urlopen(req, timeout=15) as r:
            r.read()
            return None
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


# ── Brevo email ──────────────────────────────────────────────────────────────


def _render_email_bodies(*, meta: PreviewMeta) -> tuple[str, str]:
    """Return (text_body, html_body) for the preview email."""
    url = preview_url(meta.fixture_name)
    date_str = meta.brief_date.strftime("%a %d %b %Y")
    issue_part = f" · No. {meta.issue_no}" if meta.issue_no is not None else ""

    text_lines = [
        f"Preview ready — {date_str}{issue_part}",
        "",
        f"Open: {url}",
        "",
        "URL goes live ~90s after main is pushed; manually push",
        "public/fixtures/*.json if it hasn't been.",
    ]
    if meta.todays_call:
        text_lines.extend(["", "Today's Call (draft):", meta.todays_call])

    todays_call_html = ""
    if meta.todays_call:
        paragraphs = [p.strip() for p in meta.todays_call.split("\n\n") if p.strip()]
        paragraphs_html = "".join(
            f'<p style="margin:0 0 14px;">{_html.escape(p)}</p>'
            for p in paragraphs[:-1]
        ) + (
            f'<p style="margin:0;">{_html.escape(paragraphs[-1])}</p>'
            if paragraphs else ""
        )
        todays_call_html = (
            '<hr style="border:none;border-top:1px solid #e6dfd1;margin:20px 0;">'
            '<div style="font-size:10px;letter-spacing:0.22em;'
            'text-transform:uppercase;color:#a67c2e;font-weight:600;">'
            "Today's Call (draft)"
            "</div>"
            '<div style="font-family:Georgia,serif;font-size:14px;line-height:1.65;'
            'color:#2a2620;margin-top:10px;">'
            f"{paragraphs_html}"
            "</div>"
        )

    html_body = (
        '<!DOCTYPE html>'
        '<html><body style="margin:0;padding:32px 16px;background:#f7f2e8;'
        'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1814;">'
        '<table cellpadding="0" cellspacing="0" border="0" align="center" '
        'style="max-width:600px;width:100%;background:#fdfaf4;padding:32px 28px;'
        'border:1px solid #e6dfd1;">'
        '<tr><td>'
        '<div style="font-size:10px;letter-spacing:0.22em;'
        'text-transform:uppercase;color:#a67c2e;font-weight:600;">'
        'Preview ready'
        '</div>'
        f'<div style="font-family:Georgia,serif;font-size:28px;font-weight:400;'
        f'line-height:1.15;color:#1a1814;margin-top:6px;">{_html.escape(date_str)}{_html.escape(issue_part)}</div>'
        '<hr style="border:none;border-top:1px solid #e6dfd1;margin:20px 0;">'
        f'<p style="font-size:13px;line-height:1.65;margin:0 0 6px;">'
        f'<a href="{_html.escape(url)}" '
        f'style="color:#1a1814;border-bottom:1px solid #c9b88a;text-decoration:none;">'
        f'{_html.escape(url)}</a>'
        '</p>'
        '<p style="font-size:11px;color:#7a6f5c;margin:6px 0 0;">'
        'URL goes live ~90s after main is pushed; manually push '
        '<code>public/fixtures/*.json</code> if it hasn\'t been.'
        '</p>'
        f'{todays_call_html}'
        '</td></tr></table></body></html>'
    )

    return "\n".join(text_lines), html_body


def send_email_ping(
    *,
    api_key: str,
    from_email: str,
    recipient_email: str,
    meta: PreviewMeta,
) -> str | None:
    """Send a preview-ready email via Brevo.

    Returns None on success, or a short error tag string on failure.
    """
    text_body, html_body = _render_email_bodies(meta=meta)
    issue_part = f" · No. {meta.issue_no}" if meta.issue_no is not None else ""
    subject = (
        f"[The Brief preview] {meta.brief_date.strftime('%a %d %b %Y')}{issue_part}"
    )

    payload = {
        "sender": {"email": from_email, "name": "The Brief — Preview"},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    req = Request(
        _BREVO_URL,
        data=_stdjson.dumps(payload).encode("utf-8"),
        headers={
            "api-key": api_key,
            "content-type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=30) as r:
            r.read()
            return None
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


# ── Orchestration ────────────────────────────────────────────────────────────


def notify_preview(fixture_path: str | os.PathLike[str]) -> PreviewNotifyResult:
    """Top-level: read fixture, send both pings, return a structured result.

    Reads from env:
      DISCORD_PREVIEW_WEBHOOK_URL  — Discord channel webhook
      BREVO_API_KEY                — Brevo API key (reused from notifier)
      FROM_EMAIL                   — sender (reused from notifier)
      PREVIEW_EMAIL_RECIPIENT      — single recipient (not the subscriber list)

    Each channel is attempted independently; the other still fires if one fails.
    """
    meta = extract_preview_meta(fixture_path)
    url = preview_url(meta.fixture_name)

    discord_url = os.environ.get("DISCORD_PREVIEW_WEBHOOK_URL", "").strip()
    if discord_url:
        discord_error = send_discord_ping(webhook_url=discord_url, meta=meta)
    else:
        discord_error = "no_webhook"
        logger.warning("preview_notify: DISCORD_PREVIEW_WEBHOOK_URL not set, skipping")

    brevo_key = os.environ.get("BREVO_API_KEY", "").strip()
    from_email = os.environ.get("FROM_EMAIL", "").strip()
    recipient = os.environ.get("PREVIEW_EMAIL_RECIPIENT", "").strip()
    if brevo_key and from_email and recipient:
        email_error = send_email_ping(
            api_key=brevo_key,
            from_email=from_email,
            recipient_email=recipient,
            meta=meta,
        )
    else:
        missing = [
            name for name, val in (
                ("BREVO_API_KEY", brevo_key),
                ("FROM_EMAIL", from_email),
                ("PREVIEW_EMAIL_RECIPIENT", recipient),
            ) if not val
        ]
        email_error = "missing_env: " + ",".join(missing) if missing else "unknown"
        logger.warning("preview_notify: email ping skipped (%s)", email_error)

    if discord_error:
        logger.warning("preview_notify: discord ping failed: %s", discord_error)
    else:
        logger.info("preview_notify: discord ping sent")
    if email_error:
        logger.warning("preview_notify: email ping failed: %s", email_error)
    else:
        logger.info("preview_notify: email ping sent to %s", recipient)

    return PreviewNotifyResult(
        discord_ok=discord_error is None,
        discord_error=discord_error,
        email_ok=email_error is None,
        email_error=email_error,
        preview_url=url,
    )

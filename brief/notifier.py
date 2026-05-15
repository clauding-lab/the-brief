"""Release email notifier for V6 briefs.

Sends an HTML+plain-text digest to every row in `subscribers` after a
successful `brief.cli run --publish`. Fail-open: any error logged and
swallowed; the Supabase brief is the canonical artifact.

Spec: docs/superpowers/specs/2026-05-15-release-notifier-design.md
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Subscriber:
    """One row from the public.subscribers table."""
    name: str
    email: str
    organisation: str | None


@dataclass(frozen=True)
class NotifyResult:
    """Return value from notify(); summarises what happened."""
    sent_count: int            # subscribers Brevo accepted in the API call
    skipped_count: int         # rows skipped client-side (e.g. missing email)
    message_id: str | None     # Brevo's message-id from the 2xx response
    error: str | None          # short error tag if anything failed; None on success


from datetime import date as date_t

_LENS_PHRASE = {
    "weekly_wrap": "weekly wrap",
}
_DEFAULT_LENS_PHRASE = "daily read"


def render_subject(*, issue_no: int, brief_date: date_t, lens: str | None) -> str:
    """Return the subject line for a brief release email.

    Format: "The Brief · No. {N} · {Weekday} {DD} {Mmm} {YYYY} · {lens phrase}"
    """
    lens_phrase = _LENS_PHRASE.get(lens or "", _DEFAULT_LENS_PHRASE)
    date_str = brief_date.strftime("%a %d %b %Y")
    return f"The Brief · No. {issue_no} · {date_str} · {lens_phrase}"


from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_BDT = ZoneInfo("Asia/Dhaka")
_HOSTED_URL = "https://thebrief.clauding-lab.com/"


@dataclass(frozen=True)
class BriefRow:
    """Subset of the briefs row that the notifier needs."""
    id: str
    issue_no: int
    volume: int
    brief_date: date_t
    published_at: datetime
    todays_call: str
    lens: str | None


@dataclass(frozen=True)
class NewsRow:
    """One row from the news table — used for the lead headline."""
    headline: str
    source: str
    source_url: str | None
    published_at: datetime | None


def _hhmm_bdt(ts: datetime | None) -> str:
    """Format a timestamp as HH:MM BDT. None → empty string."""
    if ts is None:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_BDT).strftime("%H:%M BDT")


def _lens_phrase(lens: str | None) -> str:
    return _LENS_PHRASE.get(lens or "", _DEFAULT_LENS_PHRASE)


def render_text(*, brief: BriefRow, lead_news: NewsRow | None) -> str:
    """Plain-text body for the release email.

    LEAD HEADLINE section is omitted entirely when lead_news is None.
    """
    lines: list[str] = []
    masthead_no = f"No. {brief.issue_no}"
    masthead_vol = f"Vol. {brief.volume:02d}"
    lines.append(f"THE BRIEF · {masthead_vol} · {masthead_no}")
    lines.append(f"{brief.brief_date.strftime('%a %d %b %Y')} · {_hhmm_bdt(brief.published_at)}  [{_lens_phrase(brief.lens)}]")
    lines.append("")

    lines.append("TODAY'S CALL")
    # todays_call may be multi-paragraph — emit as-is, preserving blank-line separators
    lines.append(brief.todays_call.strip())
    lines.append("")

    if lead_news is not None:
        lines.append("LEAD HEADLINE")
        lines.append(lead_news.headline)
        time_part = _hhmm_bdt(lead_news.published_at)
        meta = f"{lead_news.source} · {time_part}" if time_part else lead_news.source
        lines.append(meta)
        if lead_news.source_url:
            lines.append(lead_news.source_url)
        lines.append("")

    lines.append(f"Full edition → {_HOSTED_URL}")
    lines.append("")
    lines.append("---")
    lines.append("You're getting this because you subscribed at thebrief.clauding-lab.com.")
    lines.append("Unsubscribe: reply to this email with 'Unsubscribe' in the subject.")

    return "\n".join(lines)


import html as _html


def _esc(s: str) -> str:
    """HTML-escape a runtime string. Always use for user/editor-derived text."""
    return _html.escape(s, quote=True)


def render_html(*, brief: BriefRow, lead_news: NewsRow | None) -> str:
    """HTML body — single-column 600px, Outlook-safe inline styles.

    Cream-paper palette mirrors the site identity; Georgia for editorial weight,
    system sans for chrome, amber-gold (#a67c2e) section labels, hairline rules.
    """
    paragraphs = [p.strip() for p in brief.todays_call.split("\n\n") if p.strip()]
    paragraphs_html = "".join(
        f'<p style="margin:0 0 14px;">{_esc(p)}</p>' for p in paragraphs[:-1]
    ) + (f'<p style="margin:0;">{_esc(paragraphs[-1])}</p>' if paragraphs else "")

    lead_block = ""
    if lead_news is not None:
        headline_html = _esc(lead_news.headline)
        if lead_news.source_url and lead_news.source_url.startswith(("http://", "https://")):
            headline_html = (
                f'<a href="{_esc(lead_news.source_url)}" '
                f'style="color:#1a1814;text-decoration:none;border-bottom:1px solid #c9b88a;">'
                f'{headline_html}</a>'
            )
        time_part = _hhmm_bdt(lead_news.published_at)
        meta = f"{_esc(lead_news.source)} · {_esc(time_part)}" if time_part else _esc(lead_news.source)
        lead_block = (
            '<div style="font-size:10px;letter-spacing:0.16em;text-transform:uppercase;'
            'color:#a67c2e;font-weight:600;">Lead Headline</div>'
            f'<div style="font-family:Georgia,serif;font-size:18px;font-weight:400;'
            f'line-height:1.35;color:#1a1814;margin-top:10px;">{headline_html}</div>'
            f'<div style="font-size:12px;color:#7a6f5c;margin-top:6px;">{meta}</div>'
            '<hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">'
        )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:32px 16px;background:#f7f2e8;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1814;">
<table cellpadding="0" cellspacing="0" border="0" align="center" style="max-width:600px;width:100%;background:#fdfaf4;padding:32px 28px;border:1px solid #e6dfd1;">
  <tr><td>
    <div style="font-family:Georgia,serif;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#7a6f5c;">The Brief &middot; Vol. {brief.volume:02d} &middot; No. {brief.issue_no}</div>
    <div style="font-family:Georgia,serif;font-size:32px;font-weight:400;line-height:1.1;color:#1a1814;margin-top:6px;">{brief.brief_date.strftime("%a %d %b %Y")}</div>
    <div style="font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#9a8e75;margin-top:4px;">{_hhmm_bdt(brief.published_at)} &middot; {_lens_phrase(brief.lens)}</div>
    <hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">

    <div style="font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:#a67c2e;font-weight:600;">Today's Call</div>
    <div style="font-family:Georgia,serif;font-size:15px;line-height:1.65;color:#2a2620;margin-top:10px;">
      {paragraphs_html}
    </div>
    <hr style="border:none;border-top:1px solid #e6dfd1;margin:24px 0;">

    {lead_block}
    <a href="{_HOSTED_URL}" style="display:inline-block;font-size:12px;letter-spacing:0.16em;text-transform:uppercase;color:#1a1814;font-weight:600;border-bottom:2px solid #1a1814;text-decoration:none;padding-bottom:2px;">Full edition &rarr;</a>
    <div style="font-size:10px;color:#9a8e75;margin-top:20px;">You're getting this because you subscribed at thebrief.clauding-lab.com. <a href="mailto:adnan.rshd@gmail.com?subject=Unsubscribe%20-%20The%20Brief" style="color:#9a8e75;">Unsubscribe</a>.</div>
  </td></tr>
</table>
</body></html>"""


def render_email(*, brief: BriefRow, lead_news: NewsRow | None) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for a brief release email.

    Pure function — no I/O, no env reads. Use for unit-testing and dry-run rendering.
    """
    subject = render_subject(
        issue_no=brief.issue_no,
        brief_date=brief.brief_date,
        lens=brief.lens,
    )
    html = render_html(brief=brief, lead_news=lead_news)
    text = render_text(brief=brief, lead_news=lead_news)
    return subject, html, text


import os
from urllib.request import urlopen, Request


def _supabase_config() -> tuple[str, str]:
    """Same pattern as brief/v6_publisher.py::_config — service-role auth."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars. "
            "On Hetzner these come from /etc/brief.env via systemd EnvironmentFile."
        )
    return url.rstrip("/"), key


def fetch_subscribers() -> list[Subscriber]:
    """GET /rest/v1/subscribers — all rows ordered by created_at desc."""
    url, key = _supabase_config()
    req = Request(
        f"{url}/rest/v1/subscribers?select=name,email,organisation&order=created_at.desc",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=30) as r:
        rows = _json_loads(r.read())
    return [
        Subscriber(name=row["name"], email=row["email"], organisation=row.get("organisation"))
        for row in rows
    ]


def _json_loads(data: bytes) -> list[dict]:
    import json as _stdjson
    return _stdjson.loads(data.decode("utf-8"))


def _parse_iso(s: str | None) -> datetime | None:
    """Parse ISO 8601 (with or without timezone) → datetime."""
    if not s:
        return None
    # Supabase returns "2026-05-15T09:33:12.488474+00:00" — Python 3.11+ fromisoformat handles it
    return datetime.fromisoformat(s)


def fetch_brief_data(brief_id: str) -> tuple[BriefRow, NewsRow | None]:
    """GET brief row + lead news (first headlines-section row by ord)."""
    url, key = _supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }

    def _get(path: str) -> list[dict]:
        with urlopen(Request(f"{url}/rest/v1{path}", headers=headers), timeout=30) as r:
            return _json_loads(r.read())

    brief_rows = _get(f"/briefs?id=eq.{brief_id}&select=id,issue_no,volume,brief_date,published_at,todays_call,lens")
    if not brief_rows:
        raise RuntimeError(f"brief id={brief_id} not found in Supabase")
    b = brief_rows[0]
    brief = BriefRow(
        id=b["id"],
        issue_no=b["issue_no"],
        volume=b["volume"],
        brief_date=date_t.fromisoformat(b["brief_date"]),
        published_at=_parse_iso(b["published_at"]),  # type: ignore[arg-type]
        todays_call=b.get("todays_call") or "",
        lens=b.get("lens"),
    )

    section_rows = _get(f"/sections?brief_id=eq.{brief_id}&slug=eq.headlines&select=id&limit=1")
    if not section_rows:
        return brief, None
    section_id = section_rows[0]["id"]

    news_rows = _get(f"/news?section_id=eq.{section_id}&select=headline,source,source_url,published_at&order=ord.asc&limit=1")
    if not news_rows:
        return brief, None
    n = news_rows[0]
    lead = NewsRow(
        headline=n["headline"],
        source=n["source"],
        source_url=n.get("source_url"),
        published_at=_parse_iso(n.get("published_at")),
    )
    return brief, lead


import urllib.error

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def send_via_brevo(
    *,
    api_key: str,
    from_email: str,
    from_name: str,
    subscribers: list[Subscriber],
    subject: str,
    html_body: str,
    text_body: str,
) -> tuple[int, str | None, str | None]:
    """POST to Brevo's transactional API.

    Returns (sent_count, message_id, error). On any failure, sent_count is 0,
    message_id is None, error is a short string.
    """
    import json as _stdjson

    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": s.email, "name": s.name} for s in subscribers],
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
            body = _stdjson.loads(r.read().decode("utf-8"))
            return len(subscribers), body.get("messageId"), None
    except urllib.error.HTTPError as e:
        return 0, None, f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return 0, None, f"{type(e).__name__}: {e}"


import logging

logger = logging.getLogger(__name__)


def notify(brief_id: str) -> NotifyResult:
    """Top-level entry. Fail-open: any error logged and returned in NotifyResult.

    Reads BREVO_API_KEY, FROM_EMAIL, SUPABASE_URL, SUPABASE_SERVICE_KEY from env.
    """
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        logger.warning("notifier: BREVO_API_KEY not set, skipping send")
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error="no_api_key")

    from_email = os.environ.get("FROM_EMAIL", "").strip() or "noreply@example.com"

    try:
        brief, lead_news = fetch_brief_data(brief_id)
    except Exception as e:
        logger.exception("notifier: failed to fetch brief data: %s", e)
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error=f"fetch_brief: {e}")

    try:
        subscribers = fetch_subscribers()
    except Exception as e:
        logger.exception("notifier: failed to fetch subscribers: %s", e)
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error=f"fetch_subs: {e}")

    if not subscribers:
        logger.info("notifier: no subscribers, skipping send")
        return NotifyResult(sent_count=0, skipped_count=0, message_id=None, error="no_subscribers")

    subject, html_body, text_body = render_email(brief=brief, lead_news=lead_news)

    sent_count, message_id, error = send_via_brevo(
        api_key=api_key,
        from_email=from_email,
        from_name="The Brief",
        subscribers=subscribers,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    if error:
        logger.error("notifier: Brevo send failed: %s", error)
    else:
        logger.info("notifier: sent=%d message_id=%s", sent_count, message_id)

    return NotifyResult(
        sent_count=sent_count,
        skipped_count=0,
        message_id=message_id,
        error=error,
    )

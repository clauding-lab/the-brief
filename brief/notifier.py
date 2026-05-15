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

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

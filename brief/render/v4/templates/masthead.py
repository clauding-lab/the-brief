"""V4 masthead template — fd-meta (VOL · ISSUE · date) + fd-head 2-col layout."""
from __future__ import annotations

import html
from datetime import date
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from brief.pipeline import RunResult

_BDT_TZ = ZoneInfo("Asia/Dhaka")

_EM_DASH = "—"
_DEFAULT_BYLINE = "Desk Editor · The Brief"


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _today_bdt() -> date:
    """Return today's date in BDT."""
    from datetime import datetime
    return datetime.now(tz=_BDT_TZ).date()


def _format_date(d: date) -> str:
    """Format date as 'Tue 24 Apr 2026'."""
    return d.strftime("%a %d %b %Y")


def render_masthead(run_result: "RunResult") -> str:
    """Masthead: fd-meta (VOL · ISSUE · date) + fd-head 2-col (giant title + Today's Call)."""
    today = _today_bdt()
    today_iso = today.isoformat()
    today_display = _format_date(today)

    # fd-meta
    fd_meta_html = (
        '<div class="fd-meta">'
        "<span>VOL. II</span>"
        "<span>·</span>"
        "<span>NO. 412</span>"
        "<span>·</span>"
        f'<time datetime="{_esc(today_iso)}">{_esc(today_display)}</time>'
        "</div>"
    )

    # Today's Call block
    tc = run_result.todays_call
    if tc is not None:
        tc_text = _esc(tc.text)
        tc_byline = _esc(tc.byline)
    else:
        tc_text = _EM_DASH
        tc_byline = _esc(_DEFAULT_BYLINE)

    todays_call_html = (
        '<aside class="todays-call">'
        '<div class="tc-label">TODAY\'S CALL</div>'
        f'<p class="tc-text">{tc_text}</p>'
        f'<div class="tc-byline">{tc_byline}</div>'
        "</aside>"
    )

    # fd-title
    fd_title_html = (
        '<div class="fd-title">'
        '<h1>The <em class="italic-ox">Brief</em></h1>'
        '<p class="fd-subtitle">Bangladesh Economic Intelligence · Daily</p>'
        "</div>"
    )

    # fd-head (2-col)
    fd_head_html = (
        '<div class="fd-head">'
        + fd_title_html
        + todays_call_html
        + "</div>"
    )

    return (
        '<section class="masthead">'
        + fd_meta_html
        + fd_head_html
        + "</section>"
    )

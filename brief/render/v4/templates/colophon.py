"""V4 colophon template — brand + source list + next edition timestamp."""
from __future__ import annotations

import html
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from brief.pipeline import RunResult

_BDT_TZ = ZoneInfo("Asia/Dhaka")
_MAX_SOURCES = 10
_MORNING_BRIEF_HOUR = 6
_MORNING_BRIEF_MINUTE = 15


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def _next_edition_str(now: datetime) -> str:
    """Compute next edition timestamp.

    If now < 18:00 BDT today → tomorrow 06:15 BDT.
    If now >= 18:00 BDT today → still tomorrow 06:15 BDT (morning brief is always next day).
    Format: 'DD MMM · HH:MM BDT'  e.g. '21 Apr · 06:15 BDT'
    """
    tomorrow = now.date() + timedelta(days=1)
    next_dt_str = tomorrow.strftime("%-d %b") + f" · {_MORNING_BRIEF_HOUR:02d}:{_MORNING_BRIEF_MINUTE:02d} BDT"
    return next_dt_str


def _collect_sources(run_result: "RunResult") -> list[str]:
    """Collect unique metric sources across all sections, sorted alphabetically, capped at 10."""
    sources: set[str] = set()
    for section in run_result.sections:
        for metric in section.metrics:
            if metric.source:
                sources.add(metric.source)
    sorted_sources = sorted(sources)
    return sorted_sources[:_MAX_SOURCES]


def render_colophon(run_result: "RunResult") -> str:
    """V4 footer: brand + source list + next edition timestamp."""
    now = datetime.now(tz=_BDT_TZ)
    next_edition = _next_edition_str(now)
    sources = _collect_sources(run_result)

    # Brand column
    col_brand = (
        '<div class="col col-brand">'
        '<span class="brand">The Brief</span>'
        "</div>"
    )

    # Sources column
    if sources:
        sources_joined = _esc(" · ".join(sources))
        sources_content = f'<span class="label">Sources:</span> {sources_joined}'
    else:
        sources_content = '<span class="label">Sources:</span>'
    col_sources = (
        '<div class="col col-sources">'
        + sources_content
        + "</div>"
    )

    # Next edition column
    col_next = (
        '<div class="col col-next">'
        f"Next edition · {_esc(next_edition)}"
        "</div>"
    )

    return (
        '<footer class="colophon" role="contentinfo">'
        + col_brand
        + col_sources
        + col_next
        + "</footer>"
    )

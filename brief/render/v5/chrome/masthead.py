"""V5 masthead — magazine title + dek + TODAY'S CALL panel."""
from __future__ import annotations

import re

from brief.render.v5._jsx import _esc
from brief.schema import TodaysCall


def _trim_todays_call(text: str, max_chars: int = 320) -> str:
    """Cap Today's Call to ~3 sentences / ~320 chars for masthead alignment.

    Without this, longer Claude outputs (12+ lines) blow past the title+dek
    height in the left column and force the masthead to grow tall. Trim at
    the first sentence boundary at or after `max_chars` so we keep complete
    thoughts rather than breaking mid-clause.
    """
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Find the first sentence end at or after max_chars
    m = re.search(r"[.!?](?=\s|$)", text[max_chars:])
    if m:
        cut = max_chars + m.end()
        return text[:cut].rstrip()
    # No sentence boundary; cut at last space before max_chars
    cut = text.rfind(" ", 0, max_chars)
    return text[: cut if cut > 0 else max_chars].rstrip(",;: ") + "…"


def render_masthead(*, vol: str, issue: int, today_label: str, todays_call: TodaysCall) -> str:
    """The Brief masthead block.

    Layout (desktop): title + dek on left (1fr); TODAY'S CALL panel on right (360px).
    Title: "The" plain, "Brief," italic-oxblood, "plotted." italic-ink — all in one line break.
    """
    tc_text_trimmed = _trim_todays_call(todays_call.text)
    return (
        '<section class="masthead" aria-label="Masthead">'
        '<div class="mast-meta">'
        f'<span class="mast-meta-left">VOL. {_esc(vol)} · NO. {issue}</span>'
        '<span class="mast-meta-center">BANGLADESH · DAILY SUN-FRI</span>'
        f'<time class="mast-meta-right" datetime="{_esc(today_label)}">{_esc(today_label)}</time>'
        '</div>'
        '<div class="mast-grid">'
        '<div class="mast-title-block">'
        '<h1 class="mast-title">'
        '<span class="mt-the">The</span> '
        '<em class="mt-brief">Brief,</em><br>'
        '<em class="mt-plotted">plotted.</em>'
        '</h1>'
        '<p class="mast-dek">'
        '<em>Seven sections arranged by how much they moved and how much '
        'the book cares — not by section number.</em>'
        '</p>'
        '</div>'
        '<aside class="todays-call">'
        '<div class="tc-label">TODAY\'S CALL</div>'
        f'<p class="tc-text">{_esc(tc_text_trimmed)}</p>'
        f'<div class="tc-byline">— {_esc(todays_call.byline)}</div>'
        '</aside>'
        '</div>'
        '</section>'
    )

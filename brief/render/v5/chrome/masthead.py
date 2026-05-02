"""V5 masthead — magazine title + dek + TODAY'S CALL panel."""
from __future__ import annotations

from brief.render.v5._jsx import _esc
from brief.schema import TodaysCall


def render_masthead(*, vol: str, issue: int, today_label: str, todays_call: TodaysCall) -> str:
    """The Brief masthead block.

    Layout (desktop): title + dek on left (66%); TODAY'S CALL panel on right (33%).
    Title: "The" plain, "Brief," italic-oxblood, "plotted." italic-ink — all in one line break.
    """
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
        f'<p class="tc-text">{_esc(todays_call.text)}</p>'
        f'<div class="tc-byline">— {_esc(todays_call.byline)}</div>'
        '</aside>'
        '</div>'
        '</section>'
    )

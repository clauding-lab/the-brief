"""V5 secondary 7-card grid — 'ALSO TODAY' below the risk map."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, freshness_pill
from brief.schema import SectionData, TopPicks


def render_secondary_grid(*, picks: TopPicks, sections: dict[str, SectionData]) -> str:
    cards = []
    for entry in picks.grid:
        section = sections.get(entry.id)
        kicker = section.kicker if section else entry.id
        freshness = section.freshness if section else "unavailable"
        pill = freshness_pill(freshness)
        cards.append(
            '<a class="grid-card" data-freshness="' + _attr_esc(freshness) + '" '
            f'href="#section-{_attr_esc(entry.id)}">'
            f'<span class="grid-card-kicker">{_esc(kicker.upper())}</span>'
            f'<span class="grid-card-tldr">{_esc(entry.tldr)}</span>'
            f'<span class="grid-card-meta">{pill}<span class="grid-card-arrow">→</span></span>'
            '</a>'
        )

    return (
        '<section class="secondary-grid" aria-label="Other sections today">'
        '<header class="sg-header">ALSO TODAY · 7 SECTIONS NOT ON THE MAP</header>'
        f'<div class="sg-grid">{"".join(cards)}</div>'
        '</section>'
    )

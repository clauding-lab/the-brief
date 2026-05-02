"""V5 flow index — 'The flow, as plotted' editorial table-of-contents.

Renders a 7-column strip listing today's plotted sections in Claude's chosen
order (significance × movement, not by section number). Each cell shows:
  - 01..07 rank (big oxblood italic serif)
  - §NN · KICKER (mono caps eyebrow)
  - section title fragment (serif bold, with italic em on the predicate)

Sits AFTER the map+snapshot row and BEFORE the per-section chapters.
"""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _attr_esc, _esc
from brief.schema import TopPicks


def render_flow_index(*, picks: TopPicks, sections: dict[str, dict[str, Any]],
                      section_titles: dict[str, str]) -> str:
    """Build the flow-index HTML.

    `sections` provides {kicker, n} per id (same lookup the risk map uses).
    `section_titles` provides the long-form section title (e.g. "Iran War & Oil").
    Headlines is filtered out since it's never plotted.
    """
    plotted = [p for p in picks.plotted if p.id != "headlines"]
    if not plotted:
        return ""

    items = []
    for i, p in enumerate(plotted, start=1):
        meta = sections.get(p.id, {"kicker": p.id, "n": ""})
        kicker_short = str(meta["kicker"]).split(" · ")[0]
        title = section_titles.get(p.id, str(meta["kicker"]))
        items.append(
            '<li>'
            f'<a class="fi-jump" href="#section-{_attr_esc(p.id)}">'
            f'<div class="rank">{i:02d}</div>'
            f'<div class="kicker">§{_esc(meta["n"])} · {_esc(kicker_short)}</div>'
            f'<div class="sec">{_esc(title)}</div>'
            '</a>'
            '</li>'
        )

    return (
        '<section class="flow-idx" aria-label="The flow — as plotted">'
        '<div class="fi-h">'
        '<span class="t"><em>The flow</em> — as plotted</span>'
        '<span>Ordered by significance × movement · not by section number</span>'
        '</div>'
        f'<ol>{"".join(items)}</ol>'
        '</section>'
    )
